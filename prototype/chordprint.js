/* ============================================================================
   Chordprint — train on a Hooktheory progression corpus, encode ChordCat
   players, match people. Zero dependencies. Runs in Node and the browser.

   PIPELINE
     1. adaptHooktheory(raw)   your JSON  -> [{id,title,artist,genres,roman[]}]
     2. buildCorpus(songs)     songs      -> model {vocab, idf, clusters, ...}
     3. midiToRoman(...)       ChordCat   -> roman numerals
     4. encodeUser(...)        roman+perf -> profile
     5. match(a, b, model)     two people -> score + the reason why

   THE IDEA: two people who both play I-V-vi-IV share nothing (half of pop
   does that). Two people who both play bVI-bVII-i have found each other.
   The corpus exists to tell you which progressions are rare.
   ========================================================================= */
(function (root) {
'use strict';

/* ---------------------------------------------------------------- utils */

function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;var t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function dot(a,b){var s=0,k;if(Object.keys(a).length>Object.keys(b).length){var t=a;a=b;b=t}for(k in a)if(b[k])s+=a[k]*b[k];return s}
function norm(v){var s=0,k;for(k in v)s+=v[k]*v[k];s=Math.sqrt(s);if(!s)return v;for(k in v)v[k]/=s;return v}
function clamp(x,lo,hi){return x<lo?lo:x>hi?hi:x}

/* ------------------------------------------------- 1. roman numerals ----

   Canonical token. Case carries quality (ii = minor, II = major), accidental
   prefix carries borrowing (bVII), suffix carries extension (ii7, IM7).
   Inversions are dropped; secondary function (V/V) is kept.
   Lossy on purpose: we want C-Am-F-G and G-Em-C-D to collide.            */

var QUALITY_ALIAS = {
  'maj7':'M7','M7':'M7','Δ7':'M7','Δ':'M7','major7':'M7','ma7':'M7',
  'min7':'7','m7':'7','-7':'7',
  'dim':'°','o':'°','°':'°',
  'dim7':'°7','o7':'°7','°7':'°7',
  'm7b5':'ø7','ø':'ø7','ø7':'ø7','hdim7':'ø7',
  'aug':'+','+':'+','#5':'+',
  'sus':'sus4','sus4':'sus4','sus2':'sus2',
  '6':'6','7':'7','9':'9','11':'11','13':'13','add9':'add9','':''
};

function normalizeRoman(tok){
  if(tok==null) return null;
  var s=String(tok).trim().replace(/\s+/g,'');
  if(!s) return null;
  var secondary='';
  var slash=s.indexOf('/');
  if(slash>=0){
    var tail=s.slice(slash+1);
    if(/^[b#]?[ivIV]+$/.test(tail)) secondary='/'+tail;   // V/V  -> keep
    s=s.slice(0,slash);                                    // I/3  -> drop
  }
  var m=s.match(/^([b#]?)([ivIV]+)(.*)$/);
  if(!m) return null;
  var acc=m[1], num=m[2], suf=m[3];
  var isMinor = num===num.toLowerCase();
  var q=QUALITY_ALIAS[suf]!==undefined?QUALITY_ALIAS[suf]:suf;
  if(suf==='min7'||suf==='m7'||suf==='-7'){isMinor=true;q='7'}
  num = isMinor?num.toLowerCase():num.toUpperCase();
  return acc+num+q+secondary;
}

function romanInfo(tok){
  var m=String(tok).match(/^([b#]?)([ivIV]+)(.*?)(\/[b#]?[ivIV]+)?$/);
  if(!m) return {chromatic:false,extended:false,minor:false,degree:null};
  var acc=m[1],num=m[2],suf=m[3]||'',sec=m[4]||'';
  return {
    chromatic: !!acc || !!sec,
    extended : /7|9|11|13|M7|ø/.test(suf),
    minor    : num===num.toLowerCase(),
    degree   : acc+num.toUpperCase()
  };
}

/* --------------------------------------------------------- 2. n-grams */

function ngrams(seq, sizes){
  sizes = sizes || [2,3];
  var out={}, i, n, j, g;
  for(j=0;j<sizes.length;j++){
    n=sizes[j];
    for(i=0;i+n<=seq.length;i++){
      g=seq.slice(i,i+n).join('>');
      out[g]=(out[g]||0)+1;
    }
  }
  return out;
}

/* ------------------------------------------------------ 3. the corpus */

/* Swap this one function when the real Hooktheory JSON lands. Everything
   downstream only ever sees {id,title,artist,genres,roman[]}.            */
function adaptHooktheory(raw){
  var rows = Array.isArray(raw) ? raw : (raw.songs||raw.data||raw.results||[]);
  var out=[],i,r,seq;
  for(i=0;i<rows.length;i++){
    r=rows[i];
    seq = r.roman || r.chords || r.progression || r.chord_progression || r.hr || [];
    if(typeof seq==='string') seq=seq.split(/[\s,>|\-]+/);
    seq=(seq||[]).map(normalizeRoman).filter(Boolean);
    if(seq.length<2) continue;
    var g=r.genres||r.genre||r.tags||[];
    if(typeof g==='string') g=[g];
    out.push({
      id: r.id||r.song_id||('s'+i),
      title: r.title||r.song||r.name||('untitled '+i),
      artist: r.artist||r.band||'',
      genres: g,
      roman: seq
    });
  }
  return out;
}

function buildCorpus(songs, opts){
  opts=opts||{};
  var K=opts.k||12, sizes=opts.ngramSizes||[2,3], seed=opts.seed||42;
  var df={}, docs=[], i, g;

  for(i=0;i<songs.length;i++){
    var tf=ngrams(songs[i].roman,sizes);
    docs.push(tf);
    for(g in tf) df[g]=(df[g]||0)+1;
  }

  var N=songs.length, idf={};
  for(g in df) idf[g]=Math.log(1+N/df[g]);          // rare -> heavy

  // where does each progression live: which songs, which genres
  var ngramIndex={};
  for(i=0;i<docs.length;i++){
    for(g in docs[i]){
      if(!ngramIndex[g]) ngramIndex[g]={songs:[],genres:{}};
      if(ngramIndex[g].songs.length<8) ngramIndex[g].songs.push(songs[i].title);
      var gs=songs[i].genres;
      for(var j=0;j<gs.length;j++) ngramIndex[g].genres[gs[j]]=(ngramIndex[g].genres[gs[j]]||0)+1;
    }
  }

  var vecs=docs.map(function(tf){
    var v={},k;
    for(k in tf) v[k]=(1+Math.log(tf[k]))*idf[k];
    return norm(v);
  });

  var km = sphericalKMeans(vecs,K,seed,opts.iters||25);
  var clusters = nameClusters(km,songs,idf);

  return {
    n:N, idf:idf, df:df, ngramSizes:sizes,
    centroids:km.centroids, clusters:clusters, ngramIndex:ngramIndex
  };
}

/* ------------------------------------ 4. k-means over the CORPUS, not
   over your users. 30 users cluster into noise; 20k songs cluster into
   real harmonic families, and a user is then a distribution over them.
   That is what makes matching work with two people in the database.    */

function sphericalKMeans(vecs,K,seed,iters){
  var rnd=mulberry32(seed), n=vecs.length, i,j,c;
  K=Math.min(K,n);

  // k-means++ seeding, cosine distance
  var centroids=[vecs[Math.floor(rnd()*n)]];
  while(centroids.length<K){
    var d2=[],tot=0;
    for(i=0;i<n;i++){
      var best=-1;
      for(c=0;c<centroids.length;c++) best=Math.max(best,dot(vecs[i],centroids[c]));
      var d=1-best; d=d*d; d2.push(d); tot+=d;
    }
    var r=rnd()*tot, acc=0, pick=n-1;
    for(i=0;i<n;i++){acc+=d2[i]; if(acc>=r){pick=i;break}}
    centroids.push(vecs[pick]);
  }

  var assign=new Array(n).fill(0);
  for(var it=0;it<iters;it++){
    var moved=0;
    for(i=0;i<n;i++){
      var bi=0,bs=-Infinity;
      for(c=0;c<K;c++){var s=dot(vecs[i],centroids[c]); if(s>bs){bs=s;bi=c}}
      if(assign[i]!==bi){assign[i]=bi;moved++}
    }
    var sums=[],counts=new Array(K).fill(0);
    for(c=0;c<K;c++) sums.push({});
    for(i=0;i<n;i++){
      var v=vecs[i],t=sums[assign[i]];
      for(j in v) t[j]=(t[j]||0)+v[j];
      counts[assign[i]]++;
    }
    for(c=0;c<K;c++) if(counts[c]) centroids[c]=norm(sums[c]);
    if(!moved) break;
  }
  return {centroids:centroids, assign:assign, k:K};
}

function nameClusters(km,songs,idf){
  var out=[],c,i;
  for(c=0;c<km.k;c++){
    var members=[],genres={};
    for(i=0;i<songs.length;i++) if(km.assign[i]===c){
      members.push(songs[i]);
      for(var j=0;j<songs[i].genres.length;j++){
        var g=songs[i].genres[j]; genres[g]=(genres[g]||0)+1;
      }
    }
    var top=Object.keys(km.centroids[c]).sort(function(a,b){
      return km.centroids[c][b]-km.centroids[c][a];
    }).slice(0,4);
    var topGenres=Object.keys(genres).sort(function(a,b){return genres[b]-genres[a]}).slice(0,2);
    out.push({
      id:c, size:members.length,
      signature:top,
      genres:topGenres,
      label: topGenres.length ? topGenres.join(' / ') : (top[0]||'cluster '+c),
      examples: members.slice(0,3).map(function(s){return s.title})
    });
  }
  return out;
}

/* ------------------------------- 5. ChordCat MIDI -> roman numerals ---- */

var TEMPLATES=[
  ['',      [0,4,7]],      ['m',   [0,3,7]],      ['°',  [0,3,6]],
  ['+',     [0,4,8]],      ['sus2',[0,2,7]],      ['sus4',[0,5,7]],
  ['M7',    [0,4,7,11]],   ['7',   [0,4,7,10]],   ['m7', [0,3,7,10]],
  ['ø7',    [0,3,6,10]],   ['°7',  [0,3,6,9]],    ['6',  [0,4,7,9]],
  ['m6',    [0,3,7,9]],    ['add9',[0,2,4,7]],
  ['M9',    [0,4,7,11,2]], ['9',   [0,4,7,10,2]], ['m9', [0,3,7,10,2]]
];
var PITCH={C:0,'C#':1,Db:1,D:2,'D#':3,Eb:3,E:4,F:5,'F#':6,Gb:6,G:7,'G#':8,Ab:8,A:9,'A#':10,Bb:10,B:11};
var DEGREE={0:'I',1:'bII',2:'II',3:'bIII',4:'III',5:'IV',6:'bV',7:'V',8:'bVI',9:'VI',10:'bVII',11:'VII'};

/* notes: array of MIDI note numbers sounding together */
function chordFromNotes(notes,tonicPc){
  if(!notes||!notes.length) return null;
  var pcs={},i;
  for(i=0;i<notes.length;i++) pcs[((notes[i]%12)+12)%12]=true;
  var present=Object.keys(pcs).map(Number);
  if(present.length<2) return null;
  var bass=Math.min.apply(null,notes)%12;

  var best=null;
  for(i=0;i<present.length;i++){
    var rootPc=present[i];
    for(var t=0;t<TEMPLATES.length;t++){
      var name=TEMPLATES[t][0], iv=TEMPLATES[t][1];
      var want={},k;
      for(k=0;k<iv.length;k++) want[(rootPc+iv[k])%12]=true;
      var inter=0,wk=Object.keys(want);
      for(k=0;k<wk.length;k++) if(pcs[wk[k]]) inter++;
      var union=Object.keys(want).length+present.length-inter;
      var score=inter/union;
      if(rootPc===bass) score+=0.08;              // bass is usually the root
      if(!best||score>best.score) best={score:score,root:rootPc,q:name};
    }
  }
  if(!best||best.score<0.5) return null;

  var semis=((best.root-tonicPc)%12+12)%12;
  var num=DEGREE[semis];
  var minorish = best.q==='m'||best.q==='m7'||best.q==='m9'||best.q==='m6'||best.q==='°'||best.q==='°7'||best.q==='ø7';
  var suffix = best.q==='m'?'':best.q==='m7'?'7':best.q==='m9'?'9':best.q==='m6'?'6':best.q;
  var acc='', body=num;
  var am=num.match(/^([b#])(.+)$/);
  if(am){acc=am[1];body=am[2]}
  return normalizeRoman(acc+(minorish?body.toLowerCase():body)+suffix);
}

/* events: [{t_ms, notes:[...]}] already grouped, or raw note_on list */
function midiToRoman(events,key,mode,opts){
  opts=opts||{};
  var tonic = typeof key==='number'?key:(PITCH[key]!==undefined?PITCH[key]:0);
  var win=opts.windowMs||90, groups=[],i;

  if(events.length && events[0].notes){
    groups=events;
  } else {                                        // group note_ons by time
    var cur=null;
    for(i=0;i<events.length;i++){
      var e=events[i];
      if(!cur||e.t_ms-cur.t_ms>win){cur={t_ms:e.t_ms,notes:[]};groups.push(cur)}
      cur.notes.push(e.note!==undefined?e.note:e.pitch);
    }
  }

  var seq=[],meta=[];
  for(i=0;i<groups.length;i++){
    var r=chordFromNotes(groups[i].notes,tonic);
    if(!r) continue;
    if(seq.length && seq[seq.length-1]===r) continue;   // held chord, not a move
    seq.push(r);
    meta.push(groups[i]);
  }
  return {roman:seq,groups:meta};
}

/* ------------------------------------------------ 6. encode a player --- */

/* Fixed normalisation ranges, not z-scores: with 30 users a population
   mean is noise. These are hand-set from what a ChordCat session looks
   like — widen them if your data says otherwise.                        */
var FEATURES=[
  ['extension_rate',   0,   1  ],
  ['chromaticism',     0,   0.5],
  ['minor_ratio',      0,   1  ],
  ['tempo_bpm',        60,  180],
  ['harmonic_rhythm',  0.1, 4  ],
  ['velocity_mean',    40,  120],
  ['velocity_range',   0,   80 ],
  ['voicing_density',  2,   6  ],
  ['register_mean',    36,  84 ],
  ['exploration',      0,   1  ],
  ['repetition',       0,   1  ],
  ['loop_bars',        2,   16 ]
];

function encodeUser(o,model){
  var roman=(o.roman||[]).map(normalizeRoman).filter(Boolean);
  var tf=ngrams(roman,model.ngramSizes), g;

  // rarity-weighted progression vector, using the CORPUS idf.
  // unseen progression -> max rarity: you invented something.
  var maxIdf=Math.log(1+model.n);
  var vec={},rare={};
  for(g in tf){
    var w=(model.idf[g]!==undefined)?model.idf[g]:maxIdf;
    vec[g]=(1+Math.log(tf[g]))*w;
    rare[g]=w;
  }
  norm(vec);

  // soft membership over harmonic families
  var sims=model.centroids.map(function(c){return dot(vec,c)});
  var T=0.12, mx=Math.max.apply(null,sims), sum=0;
  var dist=sims.map(function(s){var e=Math.exp((s-mx)/T);sum+=e;return e});
  dist=dist.map(function(e){return e/sum});

  // harmonic descriptors straight off the numerals
  var ext=0,chrom=0,min=0;
  for(var i=0;i<roman.length;i++){
    var inf=romanInfo(roman[i]);
    if(inf.extended)ext++; if(inf.chromatic)chrom++; if(inf.minor)min++;
  }
  var L=Math.max(1,roman.length);
  var uniq=Object.keys(roman.reduce(function(a,r){a[r]=1;return a},{})).length;

  var p=o.perf||{};
  var feats={
    extension_rate: ext/L,
    chromaticism:   chrom/L,
    minor_ratio:    min/L,
    tempo_bpm:      p.tempo_bpm||100,
    harmonic_rhythm:p.harmonic_rhythm||1,
    velocity_mean:  p.velocity_mean||80,
    velocity_range: p.velocity_range||30,
    voicing_density:p.voicing_density||3.5,
    register_mean:  p.register_mean||60,
    exploration:    uniq/L,
    repetition:     1-(uniq/L),
    loop_bars:      p.loop_bars||4
  };

  var dense=FEATURES.map(function(f){
    return clamp((feats[f[0]]-f[1])/(f[2]-f[1]),0,1);
  });

  /* Which features did we ACTUALLY observe? Anything not measured falls back
     to a default, and defaults are identical for everyone — so if you compare
     them you are scoring people as similar for data you never collected.
     Three harmonic features always come off the numerals; the rest only
     count if the capture layer supplied them.                              */
  var ALWAYS={extension_rate:1,chromaticism:1,minor_ratio:1,exploration:1,repetition:1};
  var mask=FEATURES.map(function(f){
    return (ALWAYS[f[0]] || p[f[0]]!==undefined) ? 1 : 0;
  });

  return {
    id:o.id, name:o.name||o.id,
    roman:roman, vec:vec, rare:rare, dist:dist,
    features:feats, dense:dense, mask:mask,
    genres:o.genres||[]      // declared: what chords can never tell you
  };
}

/* ------------------------------------------------------- 7. matching --- */

var W={prog:0.45, cluster:0.25, style:0.20, comp:0.10};

function weightedJaccard(a,b){
  var inter=0,uni=0,k,seen={};
  for(k in a.rare){seen[k]=1; var bw=b.rare[k]||0; inter+=Math.min(a.rare[k],bw); uni+=Math.max(a.rare[k],bw)}
  for(k in b.rare) if(!seen[k]) uni+=b.rare[k];
  return uni?inter/uni:0;
}
function cosineArr(a,b){var s=0,na=0,nb=0;for(var i=0;i<a.length;i++){s+=a[i]*b[i];na+=a[i]*a[i];nb+=b[i]*b[i]}return(na&&nb)?s/Math.sqrt(na*nb):0}

/* NOT cosine. Every dense feature is already scaled to 0..1 and all-positive,
   and cosine between all-positive vectors has a floor around 0.6 — a punk
   player and a jazz player came out "0.65 similar", which is nonsense.
   Mean absolute distance uses the whole 0..1 range.                        */
function styleSim(a,b,ma,mb){
  var s=0,n=0;
  for(var i=0;i<a.length;i++){
    if(ma&&mb&&!(ma[i]&&mb[i])) continue;   // one of us never measured this
    s+=Math.abs(a[i]-b[i]); n++;
  }
  return n?1-(s/n):0.5;                      // nothing shared -> say so, don't guess
}

function bell(d){return 4*d*(1-d)}      // peaks at d=0.5: alike, not identical

function match(a,b,model,weights){
  var w=weights||W;
  var prog=weightedJaccard(a,b);
  var cluster=cosineArr(a.dist,b.dist);
  var style=styleSim(a.dense,b.dense,a.mask,b.mask);

  var ia=FEATURES.map(function(f){return f[0]}).indexOf('exploration');
  var comp=bell(Math.abs(a.dense[ia]-b.dense[ia]));

  var score=w.prog*prog + w.cluster*cluster + w.style*style + w.comp*comp;

  return {
    a:a.id, b:b.id, score:score,
    components:{harmonic:prog, family:cluster, style:style, complementarity:comp},
    shared: sharedProgressions(a,b,model,3),
    roles: {a:roleOf(a), b:roleOf(b)}
  };
}

/* the reason, which is the actual product — nobody connects to 0.87 */
function sharedProgressions(a,b,model,topN){
  var out=[],k;
  for(k in a.rare) if(b.rare[k]!==undefined){
    var idx=model.ngramIndex[k];
    out.push({
      ngram:k,
      rarity:Math.min(a.rare[k],b.rare[k]),
      pctOfCorpus: model.df[k] ? (100*model.df[k]/model.n) : 0,
      songs: idx?idx.songs.slice(0,3):[],
      genres: idx?Object.keys(idx.genres).sort(function(x,y){return idx.genres[y]-idx.genres[x]}).slice(0,2):[]
    });
  }
  out.sort(function(x,y){return y.rarity-x.rarity});
  return out.slice(0,topN||3);
}

function roleOf(u){
  var i=FEATURES.map(function(f){return f[0]}).indexOf('exploration');
  return u.dense[i]>0.62?'explorer':u.dense[i]<0.38?'loop-builder':'balanced';
}

/* plain-language reason. Feed this to the LLM to make it sound human. */
function reason(m){
  if(!m.shared.length) return 'Different harmonic worlds — nothing rare in common yet.';
  var s=m.shared[0];
  var bits=['You both play '+s.ngram.split('>').join('–')];
  if(s.pctOfCorpus) bits.push('only '+s.pctOfCorpus.toFixed(1)+'% of songs do');
  if(s.songs.length) bits.push('it\'s the move in "'+s.songs[0]+'"');
  var r=m.roles;
  if(r.a!==r.b) bits.push('and you\'re a '+r.a+' where they\'re a '+r.b);
  return bits.join(', ')+'.';
}

function rank(me,others,model,weights){
  return others.filter(function(o){return o.id!==me.id})
    .map(function(o){var m=match(me,o,model,weights);m.reason=reason(m);return m})
    .sort(function(x,y){return y.score-x.score});
}

/* --------------------------------------------------------- 8. export --- */

var API={
  normalizeRoman:normalizeRoman, romanInfo:romanInfo, ngrams:ngrams,
  adaptHooktheory:adaptHooktheory, buildCorpus:buildCorpus,
  chordFromNotes:chordFromNotes, midiToRoman:midiToRoman,
  encodeUser:encodeUser, match:match, rank:rank, reason:reason,
  sharedProgressions:sharedProgressions, FEATURES:FEATURES, WEIGHTS:W
};
if(typeof module!=='undefined'&&module.exports) module.exports=API;
root.Chordprint=API;

})(typeof globalThis!=='undefined'?globalThis:this);

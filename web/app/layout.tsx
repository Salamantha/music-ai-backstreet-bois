import type { Metadata } from "next";
import { Atkinson_Hyperlegible, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

/**
 * Atkinson Hyperlegible, from the Braille Institute, designed so that
 * characters which normally blur together stay distinct -- I/l/1, O/0, b/d.
 * That matters here beyond general readability: this interface is full of
 * roman numerals and note names where a misread character changes the meaning.
 */
const sans = Atkinson_Hyperlegible({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-sans",
  display: "swap",
});

/** IBM Plex Mono for chord symbols and cp tokens: clear zero, clear one. */
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "ChordCat Connect",
  description: "Find musicians who hear harmony the way you do.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>
        <a href="#main" className="skip-link">Skip to content</a>
        {children}
      </body>
    </html>
  );
}

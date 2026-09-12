"use client";

export interface StepDef {
  id: string;
  label: string;
  hint: string;
  /** False until the work this step represents has been done. */
  complete: boolean;
  /** False while the step cannot yet be reached. */
  reachable: boolean;
}

interface Props {
  steps: StepDef[];
  current: number;
  onGo: (index: number) => void;
}

/**
 * Progress through the app, one stage at a time.
 *
 * Marked up as a navigation landmark containing an ordered list, which is how
 * a screen reader announces "step 2 of 3". `aria-current="step"` identifies the
 * one being worked on, and a step that cannot be reached yet is genuinely
 * disabled rather than merely looking it -- so keyboard and pointer users meet
 * the same rules.
 */
export default function Stepper({ steps, current, onGo }: Props) {
  return (
    <nav aria-label="Progress">
      <ol className="steps">
        {steps.map((step, i) => {
          const isCurrent = i === current;
          return (
            <li key={step.id}>
              <button
                type="button"
                onClick={() => onGo(i)}
                disabled={!step.reachable}
                aria-current={isCurrent ? "step" : undefined}
                className={step.complete && !isCurrent ? "done" : undefined}
              >
                <span className="step-number" aria-hidden="true">
                  {step.complete && !isCurrent ? "✓" : i + 1}
                </span>
                <span>
                  <span className="step-label">
                    <span className="visually-hidden">
                      Step {i + 1} of {steps.length}:{" "}
                    </span>
                    {step.label}
                    {step.complete && (
                      <span className="visually-hidden"> (completed)</span>
                    )}
                  </span>
                  <span className="step-hint"> {step.hint}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

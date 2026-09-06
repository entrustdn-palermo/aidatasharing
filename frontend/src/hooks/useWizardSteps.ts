'use client';

import { useCallback, useMemo, useState } from 'react';

export interface WizardSteps {
  /** Index of the step currently on screen. */
  currentStep: number;
  /** Highest index the user has legitimately reached (completed or in progress). */
  furthestStep: number;
  /** Total number of steps in the wizard. */
  stepCount: number;
  isFirstStep: boolean;
  isLastStep: boolean;
  /** Advance one step (no-op on the last step). Raises furthestStep. */
  next: () => void;
  /** Go back one step (no-op on the first step). Preserves furthestStep. */
  back: () => void;
  /** Jump to a step the user has already reached; rejected for unseen steps. */
  goTo: (index: number) => void;
  /** Whether a given index is navigable from the stepper header. */
  canGoTo: (index: number) => boolean;
  /** Return to step 0 and reset progress (e.g. start over). */
  reset: () => void;
}

/**
 * Navigation state for a linear multi-step wizard.
 *
 * Deliberately data-agnostic: the wizard page owns its own form state (which
 * persists across steps because the component never unmounts), while this hook
 * tracks only *where* the user is and how far they've legitimately gotten. That
 * split is what makes it reusable for future guided flows — drop it in, feed it
 * a step count, and render your own step bodies.
 *
 * `furthestStep` is the guardrail: going back never lowers it, so the user can
 * revisit any step they've already filled, but can't jump ahead past steps
 * they haven't reached yet.
 */
export function useWizardSteps(stepCount: number): WizardSteps {
  const [currentStep, setCurrentStep] = useState(0);
  const [furthestStep, setFurthestStep] = useState(0);

  const next = useCallback(() => {
    // Read both values from state directly — updaters must stay pure (React
    // Strict Mode double-invokes them), so no nested setFurthestStep here.
    const advanced = Math.min(currentStep + 1, stepCount - 1);
    setCurrentStep(advanced);
    setFurthestStep((f) => Math.max(f, advanced));
  }, [currentStep, stepCount]);

  const back = useCallback(() => {
    setCurrentStep((cur) => Math.max(cur - 1, 0));
  }, []);

  const canGoTo = useCallback(
    (index: number) => index >= 0 && index < stepCount && index <= furthestStep,
    [stepCount, furthestStep],
  );

  const goTo = useCallback(
    (index: number) => {
      if (index >= 0 && index < stepCount && index <= furthestStep) {
        setCurrentStep(index);
      }
    },
    [stepCount, furthestStep],
  );

  const reset = useCallback(() => {
    setCurrentStep(0);
    setFurthestStep(0);
  }, []);

  return useMemo(
    () => ({
      currentStep,
      furthestStep,
      stepCount,
      isFirstStep: currentStep === 0,
      isLastStep: currentStep === stepCount - 1,
      next,
      back,
      goTo,
      canGoTo,
      reset,
    }),
    [currentStep, furthestStep, stepCount, next, back, goTo, canGoTo, reset],
  );
}

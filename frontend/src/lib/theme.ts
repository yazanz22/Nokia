import { useCallback, useEffect, useState } from "react";

export type ThemeChoice = "light" | "dark" | "system";

const KEY = "sentinel.theme";

/** What "system" currently resolves to. */
function systemTheme(): "light" | "dark" {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function read(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* private mode, blocked storage: fall through to the system default */
  }
  return "system";
}

function apply(choice: ThemeChoice) {
  const resolved = choice === "system" ? systemTheme() : choice;
  document.documentElement.dataset.theme = resolved;
}

/**
 * Theme state for the whole app.
 *
 * Three states rather than a boolean, because "follow the OS" is a real answer
 * and a two-way toggle cannot express it: a machine that switches to dark at
 * dusk should take the dashboard with it unless somebody has said otherwise.
 * The choice is stored per browser; the resolved value is stamped on <html> so
 * every token swap happens in one place (see styles/tokens.css).
 */
export function useTheme() {
  const [choice, setChoice] = useState<ThemeChoice>(read);

  useEffect(() => {
    apply(choice);
    try {
      localStorage.setItem(KEY, choice);
    } catch {
      /* storage unavailable: the theme still applies for this session */
    }
  }, [choice]);

  // Follow the OS while the choice is "system", and stop following the moment
  // somebody picks a side.
  useEffect(() => {
    if (choice !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [choice]);

  const cycle = useCallback(() => {
    setChoice((c) => (c === "light" ? "dark" : c === "dark" ? "system" : "light"));
  }, []);

  const resolved: "light" | "dark" =
    choice === "system" ? (typeof window === "undefined" ? "light" : systemTheme()) : choice;

  return { choice, resolved, setChoice, cycle };
}

/** Stamp the stored theme before React mounts, so there is no light flash. */
export function initTheme() {
  apply(read());
}

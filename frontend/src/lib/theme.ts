import { useCallback, useEffect, useState } from "react";

export type ThemeChoice = "light" | "dark";

const KEY = "sentinel.theme";

/** What the machine is set to, used only to pick the opening side. */
function systemTheme(): ThemeChoice {
  if (typeof window === "undefined") return "light";
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function read(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark") return v;
  } catch {
    /* private mode, blocked storage: fall through to the machine's setting */
  }
  // Nothing stored yet — which also covers the "system" that earlier builds
  // wrote here. Open on whatever the machine is set to so the first paint is
  // never a surprise, then stay where it is put.
  return systemTheme();
}

function apply(choice: ThemeChoice) {
  document.documentElement.dataset.theme = choice;
}

/**
 * Theme state for the whole app: two sides, nothing else.
 *
 * The OS preference decides the opening side on a browser that has never
 * chosen, and is not consulted again — once somebody picks a side the
 * dashboard stays on it, including across a machine's own dusk switch. The
 * chosen value is stored per browser and stamped on <html>, so every token
 * swap happens in one place (see styles/tokens.css).
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

  const toggle = useCallback(() => {
    setChoice((c) => (c === "dark" ? "light" : "dark"));
  }, []);

  return { choice, setChoice, toggle };
}

/** Stamp the stored theme before React mounts, so there is no light flash. */
export function initTheme() {
  apply(read());
}

import { Moon, Sun } from "@phosphor-icons/react";
import type { ThemeChoice } from "../lib/theme";

const NEXT_LABEL: Record<ThemeChoice, string> = {
  light: "Switch to dark theme",
  dark: "Switch to light theme",
};

const CURRENT_LABEL: Record<ThemeChoice, string> = {
  light: "Light",
  dark: "Dark",
};

/**
 * Light or dark, from one control.
 *
 * The icon shows the side currently in use; the title says what the next press
 * does, because that is the question somebody has when their pointer is already
 * on the button. The accessible name carries both, since an icon alone cannot
 * say which of the two states it is describing.
 */
export function ThemeToggle({ choice, onToggle }: { choice: ThemeChoice; onToggle: () => void }) {
  const Icon = choice === "light" ? Sun : Moon;
  return (
    <button
      className="btn btn-ghost btn-icon"
      onClick={onToggle}
      title={NEXT_LABEL[choice]}
      aria-label={`Theme: ${CURRENT_LABEL[choice]}. ${NEXT_LABEL[choice]}`}
    >
      <Icon size={16} weight="regular" aria-hidden />
    </button>
  );
}

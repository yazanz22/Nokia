import { Desktop, Moon, Sun } from "@phosphor-icons/react";
import type { ThemeChoice } from "../lib/theme";

const NEXT_LABEL: Record<ThemeChoice, string> = {
  light: "Switch to dark theme",
  dark: "Follow system theme",
  system: "Switch to light theme",
};

const CURRENT_LABEL: Record<ThemeChoice, string> = {
  light: "Light",
  dark: "Dark",
  system: "System",
};

/**
 * Light / dark / system, cycled from one control.
 *
 * Three states rather than a two-way switch because "follow the OS" is a real
 * preference and the common case: a site office that dims its screens in the
 * evening should take the dashboard with it. The title says what the next press
 * does, not what the current state is, because that is the question somebody
 * has when their pointer is already on the button.
 */
export function ThemeToggle({ choice, onCycle }: { choice: ThemeChoice; onCycle: () => void }) {
  const Icon = choice === "light" ? Sun : choice === "dark" ? Moon : Desktop;
  return (
    <button
      className="btn btn-ghost btn-icon"
      onClick={onCycle}
      title={NEXT_LABEL[choice]}
      aria-label={`Theme: ${CURRENT_LABEL[choice]}. ${NEXT_LABEL[choice]}`}
    >
      <Icon size={16} weight="regular" aria-hidden />
    </button>
  );
}

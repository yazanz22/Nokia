import { Component, type ReactNode } from "react";

/**
 * The last line of defence for a dashboard that runs unattended on a wall.
 *
 * Every websocket frame is dispatched straight into a reducer during render, and
 * `WsEvent.payload` is untyped by construction: one malformed frame throwing
 * inside that reducer unmounts the entire React root and leaves a white page
 * with no way back except a manual reload. The frames are guarded at source now
 * (see lib/ws.ts), but a guard is a claim about the frames we thought of. This
 * is what happens to the ones we did not.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, { err: Error | null }> {
  state: { err: Error | null } = { err: null };

  static getDerivedStateFromError(err: Error) {
    return { err };
  }

  componentDidCatch(err: Error) {
    // Console rather than a reporting service: there is no backend endpoint for
    // this, and swallowing it silently would hide the one artefact somebody
    // debugging afterwards actually needs.
    console.error("Dashboard crashed:", err);
  }

  render() {
    if (!this.state.err) return this.props.children;
    return (
      <div className="crash" role="alert">
        <div className="state is-error">
          <div className="state-title">The dashboard stopped updating</div>
          <p className="state-body">
            Something in the live feed could not be rendered. The site itself is
            unaffected: the agent keeps investigating and work orders keep being
            raised, this view just lost its place.
          </p>
          <p className="state-body mono text-xs">{this.state.err.message}</p>
          <button className="btn btn-primary btn-sm" onClick={() => location.reload()}>
            Reload the dashboard
          </button>
        </div>
      </div>
    );
  }
}

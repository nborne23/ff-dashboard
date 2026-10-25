// The full-screen celebration when one of the user's starters scores or breaks a big
// play (add-play-highlights). Mounted once by the shell so it plays over any screen.
//
// Distinct from Game Day's `useBigPlays` row flash, on purpose: that one is a local cue
// on whichever matchup row moved 6+ points (either side, any league), this one is
// "your guy just did it", driven by the server's stat-level detector. On Game Day both
// fire for the same touchdown — the row tells you where, the card tells you who.
//
// Motion: the card and headshot spring in with the shared `--spring-bouncy` token and
// the confetti is a hand-rolled canvas burst. Reduced motion zeroes the spring durations
// (tokens.css) and skips the confetti, leaving a plain fade.

import { useCallback, useEffect, useRef, useState } from "react";

import { describePlay, useHighlightFeed, type PlayerHighlight } from "../../api/highlights";
import { useHighlightStore } from "../../stores/highlights";
import "../../styles/highlights.css";

/** Mirrors styles/highlights.css: how long one card stays up before the next. */
export const CELEBRATION_MS = 3200;

const HEADLINES: Record<PlayerHighlight["kind"], string> = {
  touchdown: "Touchdown",
  big_play: "Big Play",
};

export function HighlightCelebration() {
  useHighlightFeed();
  useDevTrigger();
  const current = useHighlightStore((s) => s.queue[0]);
  const more = useHighlightStore((s) => (s.queue.length === 1 ? s.overflow : 0));
  const shift = useHighlightStore((s) => s.shift);

  if (!current) return null;
  // Keyed by id so the next one in line remounts and replays every entrance animation.
  return <Celebration key={current.id} highlight={current} more={more} onDone={shift} />;
}

interface CelebrationProps {
  highlight: PlayerHighlight;
  more: number;
  onDone: () => void;
}

function Celebration({ highlight, more, onDone }: CelebrationProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [headshotFailed, setHeadshotFailed] = useState(!highlight.headshot_url);

  useEffect(() => {
    const timer = setTimeout(onDone, CELEBRATION_MS);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onDone();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("keydown", onKey);
    };
  }, [onDone]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || prefersReducedMotion()) return;
    return burstConfetti(canvas, highlight.kind === "touchdown" ? 160 : 70);
  }, [highlight.kind]);

  const headline = HEADLINES[highlight.kind];
  const play = describePlay(highlight);

  return (
    <div
      className="hl"
      data-kind={highlight.kind}
      role="status"
      aria-label={`${headline}: ${highlight.player_name}, ${play}`}
      onClick={onDone}
    >
      <canvas ref={canvasRef} className="hl-confetti" aria-hidden="true" />
      <div className="hl-card">
        <div className="hl-headshot" aria-hidden="true">
          {headshotFailed ? (
            <span className="hl-initials">{initials(highlight.player_name)}</span>
          ) : (
            <img src={highlight.headshot_url} alt="" onError={() => setHeadshotFailed(true)} />
          )}
        </div>
        <div className="hl-headline">{headline}</div>
        <div className="hl-name">{highlight.player_name}</div>
        <div className="hl-play">
          {play} · {highlight.position} · {highlight.nfl_team}
        </div>
        {highlight.stat_line && <div className="hl-line">{highlight.stat_line}</div>}
        {more > 0 && <div className="hl-more">and {more} more</div>}
      </div>
    </div>
  );
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("");
}

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : true;
}

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  spin: number;
  angle: number;
  wobble: number;
  size: number;
  color: string;
}

const CONFETTI_MS = 2800;
const GRAVITY = 1400; // px/s²
const DRAG = 1.6; // per second, applied to velocity

/**
 * One burst from just above the card's center: particles leave fast and upward, drag
 * bleeds the speed off, gravity takes them down, and the last 30% fades. Physics runs
 * on elapsed time rather than per frame, so a 120 Hz iPhone and a 60 Hz laptop see the
 * same arc. Returns the cleanup.
 */
function burstConfetti(canvas: HTMLCanvasElement, count: number): () => void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return () => {};

  const dpr = window.devicePixelRatio || 1;
  const width = window.innerWidth;
  const height = window.innerHeight;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  ctx.scale(dpr, dpr);

  const style = getComputedStyle(document.documentElement);
  const palette = ["--positive", "--accent", "--live", "--text"]
    .map((name) => style.getPropertyValue(name).trim())
    .filter(Boolean);
  const colors = palette.length ? palette : ["#30d158", "#0a84ff", "#ff9f0a", "#ffffff"];

  const originX = width / 2;
  const originY = height * 0.4;
  const speed = Math.min(width, height) * 1.6;
  const particles: Particle[] = Array.from({ length: count }, () => {
    // Mostly upward: a 200° fan centered straight up.
    const direction = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 1.1;
    const velocity = speed * (0.35 + Math.random() * 0.65);
    return {
      x: originX,
      y: originY,
      vx: Math.cos(direction) * velocity,
      vy: Math.sin(direction) * velocity,
      spin: (Math.random() - 0.5) * 18,
      angle: Math.random() * Math.PI,
      wobble: Math.random() * Math.PI * 2,
      size: 6 + Math.random() * 6,
      color: colors[Math.floor(Math.random() * colors.length)]!,
    };
  });

  let frame = 0;
  let last = performance.now();
  const start = last;

  const tick = (now: number) => {
    const dt = Math.min((now - last) / 1000, 1 / 30);
    last = now;
    const elapsed = now - start;
    const fade = Math.min(1, Math.max(0, (CONFETTI_MS - elapsed) / (CONFETTI_MS * 0.3)));

    ctx.clearRect(0, 0, width, height);
    ctx.globalAlpha = fade;
    for (const p of particles) {
      const damping = Math.exp(-DRAG * dt);
      p.vx *= damping;
      p.vy = p.vy * damping + GRAVITY * dt;
      p.wobble += dt * 8;
      p.x += (p.vx + Math.sin(p.wobble) * 40) * dt;
      p.y += p.vy * dt;
      p.angle += p.spin * dt;

      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.angle);
      // Squash on one axis as it "turns over" — reads as a flat strip tumbling.
      ctx.scale(1, Math.cos(p.wobble));
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
      ctx.restore();
    }

    if (elapsed < CONFETTI_MS) frame = requestAnimationFrame(tick);
    else ctx.clearRect(0, 0, width, height);
  };
  frame = requestAnimationFrame(tick);

  return () => cancelAnimationFrame(frame);
}

/**
 * Dev only: `window.__celebrate()` / `window.__celebrate("big_play")` in the console
 * plays a sample, since a real one needs a live game.
 */
function useDevTrigger(): void {
  const enqueue = useHighlightStore((s) => s.enqueue);
  const nextId = useRef(-1);
  const celebrate = useCallback(
    (kind: PlayerHighlight["kind"] = "touchdown") => {
      const touchdown = kind === "touchdown";
      enqueue([
        {
          id: nextId.current--,
          kind,
          stat_key: touchdown ? "rec_td" : "rec_40p",
          yards: touchdown ? 34 : 57,
          stat_line: touchdown ? "6 rec · 112 yds · 2 TD" : "4 rec · 88 yds",
          player_id: "dev",
          player_name: "Ja'Marr Chase",
          position: "WR",
          nfl_team: "CIN",
          headshot_url: "",
          created_at: new Date().toISOString(),
        },
      ]);
    },
    [enqueue],
  );

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    const target = window as unknown as { __celebrate?: typeof celebrate };
    target.__celebrate = celebrate;
    return () => {
      delete target.__celebrate;
    };
  }, [celebrate]);
}

// Motion helpers for Game Day: panels that move to a new place in the grid glide there
// instead of teleporting, and the spotlight grows out of the panel that opened it.
//
// Both use the spring curves defined as CSS custom properties in tokens.css, so the
// easing lives in one place and `prefers-reduced-motion` (which zeroes the durations)
// turns every animation here off at once.

import { useLayoutEffect, useRef, type RefObject } from "react";

export interface Spring {
  easing: string;
  duration: number;
}

const FALLBACK_EASING = "cubic-bezier(0.2, 0.8, 0.2, 1)";

/** Read a spring (`--spring-<name>` and `--spring-<name>-dur`) from the root tokens.
 *  Duration 0 means "don't animate": reduced motion, or an environment with no CSS. */
export function readSpring(name: "default" | "snappy" | "bouncy"): Spring {
  if (typeof window === "undefined") return { easing: FALLBACK_EASING, duration: 0 };
  const style = getComputedStyle(document.documentElement);
  const easing = style.getPropertyValue(`--spring-${name}`).trim();
  const duration = parseFloat(style.getPropertyValue(`--spring-${name}-dur`)) || 0;
  return { easing: easing || FALLBACK_EASING, duration: easing ? duration : 0 };
}

export function canAnimate(el: Element | null): el is HTMLElement {
  return el !== null && typeof (el as HTMLElement).animate === "function";
}

/** `el.animate`, falling back to a cubic curve where `linear()` easing isn't supported. */
export function animate(
  el: HTMLElement,
  keyframes: Keyframe[],
  spring: Spring,
  id?: string,
  fill: FillMode = "none",
): Animation {
  let animation: Animation;
  try {
    animation = el.animate(keyframes, { duration: spring.duration, easing: spring.easing, fill });
  } catch {
    animation = el.animate(keyframes, { duration: spring.duration, easing: FALLBACK_EASING, fill });
  }
  if (id) animation.id = id;
  return animation;
}

/** The translate an element is currently showing from a running animation. */
function presentationOffset(el: HTMLElement): { x: number; y: number } {
  const transform = getComputedStyle(el).transform;
  if (!transform || transform === "none") return { x: 0, y: 0 };
  const matrix = new DOMMatrixReadOnly(transform);
  return { x: matrix.m41, y: matrix.m42 };
}

/**
 * FLIP for the children of `containerRef` that carry `data-flip-id`.
 *
 * After a render that changed `arrangementKey`, each child's layout position is
 * compared with where it was drawn before, and a child that moved animates from its
 * old place to its new one.
 *
 * Interruptible (§3): when a child is still in flight, the new animation starts from
 * its presentation value (old layout plus the offset currently on screen), not from
 * its old layout. Rapid re-sorts during a busy Sunday never make a panel jump.
 */
export function useFlipChildren(
  containerRef: RefObject<HTMLElement | null>,
  arrangementKey: string,
): void {
  const last = useRef(new Map<string, { x: number; y: number }>());
  const lastKey = useRef(arrangementKey);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    // Only a change of ORDER or ARRANGEMENT animates. Incidental layout shifts (a logo
    // loading, a roster growing a row) just update the record; animating those would
    // set the whole stage drifting every time the data refreshed.
    const rearranged = lastKey.current !== arrangementKey;
    lastKey.current = arrangementKey;
    const spring = readSpring("default");
    const next = new Map<string, { x: number; y: number }>();

    container.querySelectorAll<HTMLElement>(":scope > [data-flip-id]").forEach((el) => {
      const id = el.dataset.flipId!;
      const pos = { x: el.offsetLeft, y: el.offsetTop };
      next.set(id, pos);

      const prev = last.current.get(id);
      if (!rearranged || !prev || spring.duration === 0 || !canAnimate(el)) return;
      if (prev.x === pos.x && prev.y === pos.y) return;

      const running = el.getAnimations().find((a) => a.id === "flip");
      const current = running ? presentationOffset(el) : { x: 0, y: 0 };
      running?.cancel();

      const dx = prev.x + current.x - pos.x;
      const dy = prev.y + current.y - pos.y;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
      animate(
        el,
        [{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }],
        spring,
        "flip",
      );
    });

    last.current = next;
  });
}

/** The transform that maps `to` onto `from`. Uniform scale, from the top-left corner. */
export function rectTransform(from: DOMRect, to: DOMRect): string {
  const scale = from.width / to.width;
  return `translate(${from.left - to.left}px, ${from.top - to.top}px) scale(${scale})`;
}

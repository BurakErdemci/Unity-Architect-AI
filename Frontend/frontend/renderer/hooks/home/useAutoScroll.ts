import { useCallback, useRef, useState } from 'react';

/**
 * "Stick to bottom" scrolling for an append-only list (chat, console log).
 *
 * Why this is a shared hook and not an inline effect: the same pattern existed
 * three times in this tree and only ONE of them was guarded. `home.tsx:318` and
 * `TerminalPanel.tsx:101` scrolled unconditionally on every new item, so a user
 * reading older output was yanked back to the bottom; `TerminalPanel.tsx:55`
 * had the guard. Fixing one call site would have left the other two — this
 * repo's recorded failure shape is a fix that closes one of several paths.
 */

/**
 * Distance from the bottom (px) still counted as "at the bottom".
 *
 * Not zero: smooth scrolling lands a pixel or two short and sub-pixel layout
 * makes an exact comparison flip to `false` on its own, which would silently
 * disarm following forever. 40 is the value the terminal console already used.
 */
export const BOTTOM_TOLERANCE_PX = 40;

export interface AutoScroll {
  /** Sentinel element ref — render a zero-height div at the end of the list. */
  endRef: React.RefObject<HTMLDivElement>;
  /** Wire to the scrollable container's `onScroll`. */
  onScroll: (e: React.UIEvent<HTMLElement>) => void;
  /** `false` while the user is reading further up. Drives the "jump" affordance. */
  isPinned: boolean;
  /** Scrolls only when the user is still at the bottom. Returns whether it scrolled. */
  followIfPinned: () => boolean;
  /** Scrolls regardless and re-arms following — for content the user MUST see. */
  scrollToBottom: (behavior?: ScrollBehavior) => void;
  /** Re-arms following without scrolling (e.g. when switching conversations). */
  repin: () => void;
}

export const useAutoScroll = (): AutoScroll => {
  const endRef = useRef<HTMLDivElement>(null);
  // A ref as well as state: the follow decision is read inside effects that must
  // NOT re-run when it flips (re-running would scroll on the very render that
  // recorded "user scrolled away"). The state copy exists only for rendering.
  const pinnedRef = useRef(true);
  const [isPinned, setIsPinned] = useState(true);

  const setPinned = useCallback((value: boolean) => {
    pinnedRef.current = value;
    setIsPinned(prev => (prev === value ? prev : value));
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    endRef.current?.scrollIntoView({ behavior });
    setPinned(true);
  }, [setPinned]);

  const followIfPinned = useCallback(() => {
    if (!pinnedRef.current) return false;
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
    return true;
  }, []);

  const onScroll = useCallback((e: React.UIEvent<HTMLElement>) => {
    const el = e.currentTarget;
    setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < BOTTOM_TOLERANCE_PX);
  }, [setPinned]);

  const repin = useCallback(() => setPinned(true), [setPinned]);

  return { endRef, onScroll, isPinned, followIfPinned, scrollToBottom, repin };
};

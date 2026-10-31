import { useEffect, useLayoutEffect, useRef } from "react";

interface Props {
  // the active item among the siblings of the thumb
  selector: string;
  className: string;
}

// a plate behind the active item of a positioned parent, it rides to the next one
export default function SlidingThumb({ selector, className }: Props) {
  const thumb = useRef<HTMLSpanElement>(null);

  function place() {
    const element = thumb.current;
    const target = element?.parentElement?.querySelector<HTMLElement>(selector);
    if (!element) {
      return;
    }
    if (!target) {
      element.style.opacity = "0";
      return;
    }
    // a thumb that was hidden appears on its item instead of riding from the old place
    const appears = element.style.opacity !== "1";
    if (appears) {
      element.style.transition = "none";
    }
    element.style.width = `${target.offsetWidth}px`;
    element.style.height = `${target.offsetHeight}px`;
    element.style.transform = `translate(${target.offsetLeft}px, ${target.offsetTop}px)`;
    element.style.opacity = "1";
    if (appears) {
      // the jump has to reach the screen before the transition is back
      void element.offsetWidth;
      element.style.transition = "";
    }
  }

  // the active item is known from the render of the parent, so every render is checked
  useLayoutEffect(place);

  useEffect(() => {
    const parent = thumb.current?.parentElement;
    if (!parent) {
      return;
    }
    let current = true;
    const observer = new ResizeObserver(() => place());
    observer.observe(parent);
    // Inter arrives after the first paint and changes the width of the items
    void document.fonts.ready.then(() => current && place());
    return () => {
      current = false;
      observer.disconnect();
    };
  }, [selector]);

  return <span ref={thumb} className={`sliding-thumb ${className}`} aria-hidden="true" />;
}

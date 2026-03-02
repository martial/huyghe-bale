import { ref, onUnmounted } from "vue";

export interface DragConstraints {
  minX?: number;
  maxX?: number;
  minY?: number;
  maxY?: number;
}

export function useDraggable(
  onDrag: (dx: number, dy: number, x: number, y: number) => void,
  onEnd?: () => void,
) {
  const dragging = ref(false);
  let startX = 0;
  let startY = 0;

  function onMouseDown(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    dragging.value = true;
    startX = e.clientX;
    startY = e.clientY;
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }

  function onMouseMove(e: MouseEvent) {
    if (!dragging.value) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    onDrag(dx, dy, e.clientX, e.clientY);
    startX = e.clientX;
    startY = e.clientY;
  }

  function onMouseUp() {
    dragging.value = false;
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
    onEnd?.();
  }

  onUnmounted(() => {
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
  });

  return { dragging, onMouseDown };
}

import { create } from "zustand";

export interface Notification {
  id: string;
  type: "success" | "error" | "info";
  message: string;
}

interface NotificationState {
  notifications: Notification[];
  notify: (type: Notification["type"], message: string) => void;
  dismiss: (id: string) => void;
}

export const useNotificationStore = create<NotificationState>((set) => ({
  notifications: [],
  notify: (type, message) => {
    const id = Math.random().toString(36).substring(2, 9);
    set((state) => ({
      notifications: [...state.notifications, { id, type, message }],
    }));
    // Auto dismiss after 3 seconds
    setTimeout(() => {
      set((state) => ({
        notifications: state.notifications.filter((n) => n.id !== id),
      }));
    }, 3000);
  },
  dismiss: (id) =>
    set((state) => ({
      notifications: state.notifications.filter((n) => n.id !== id),
    })),
}));

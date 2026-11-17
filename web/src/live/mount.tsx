// Mounts a live app with the same TanStack Query setup as the walkthrough (refetch every 3 s and on
// focus, everything invalidated after each button), so both windows stay fresh without reloading.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React, { ReactNode } from 'react';
import { createRoot } from 'react-dom/client';

import '../styles.css';

export function mount(app: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { refetchInterval: 3000, refetchOnWindowFocus: true, staleTime: 1000, retry: 1 } },
  });
  createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>{app}</QueryClientProvider>
    </React.StrictMode>,
  );
}

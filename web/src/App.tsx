import { Button } from '@westpac/ui/button';
import { Footer } from '@westpac/ui/footer';
import { Header } from '@westpac/ui/header';
import { useEffect, useState } from 'react';

import { ActionsPage } from './pages/Actions';
import { HomePage } from './pages/Home';
import { LedgerPage } from './pages/Ledger';
import { PolicyPage } from './pages/Policy';

export const PAGES = [
  { path: '/', label: 'Home', Page: HomePage },
  { path: '/ledger', label: 'Ledger (C)', Page: LedgerPage },
  { path: '/policy', label: 'Policy (D)', Page: PolicyPage },
  { path: '/actions', label: 'Actions (E)', Page: ActionsPage },
] as const;

/** Hash routing (#/ledger ...): no router library, and app.py can serve web/dist as plain files. */
function currentPath(): string {
  const path = window.location.hash.replace(/^#/, '') || '/';
  return PAGES.some(p => p.path === path) ? path : '/';
}

export function useHashPath(): string {
  const [path, setPath] = useState(currentPath);
  useEffect(() => {
    const onChange = () => {
      setPath(currentPath());
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return path;
}

export function App() {
  const path = useHashPath();
  const { Page } = PAGES.find(p => p.path === path) ?? PAGES[0];

  return (
    <div className="flex min-h-screen flex-col bg-background-pale">
      <Header brand="wbc" logoLink="#/" logoAssistiveText="Customer Guardian home" skipToContentId="#main">
        <span className="typography-body-10 text-text-muted">Customer Guardian</span>
      </Header>
      <nav aria-label="Pages" className="border-b border-border-muted bg-background-white">
        <ul className="mx-auto flex max-w-lg gap-1 overflow-x-auto px-2 py-1 sm:px-3">
          {PAGES.map(p => {
            const active = p.path === path;
            return (
              <li key={p.path} className="shrink-0">
                <Button
                  tag="a"
                  href={`#${p.path}`}
                  look={active ? 'primary' : 'faint'}
                  soft={!active}
                  size="medium"
                  aria-current={active ? 'page' : undefined}
                >
                  {p.label}
                </Button>
              </li>
            );
          })}
        </ul>
      </nav>
      <main id="main" className="mx-auto w-full max-w-lg flex-1 px-2 py-4 sm:px-3">
        <Page />
      </main>
      <Footer brand="wbc" logoAssistiveText="Westpac">
        <p className="typography-body-10">
          Customer Guardian · Westpac Hackathon prototype · demo data only, no real customers
        </p>
      </Footer>
    </div>
  );
}

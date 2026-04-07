import { useLocation } from 'react-router';

export function FrontendShell() {
  const location = useLocation();

  return (
    <main>
      <section>
        <p>Superwriter frontend baseline</p>
        <h1>React workspace is ready for route migration.</h1>
        <p>
          Current path: <code>{location.pathname}</code>
        </p>
      </section>
    </main>
  );
}

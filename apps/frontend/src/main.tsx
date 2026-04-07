import React from 'react';
import ReactDOM from 'react-dom/client';

import { AppProviders } from './providers/AppProviders';

const rootElement = document.getElementById('root');

if (!rootElement) {
  throw new Error('Missing #root element for frontend bootstrap.');
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <AppProviders />
  </React.StrictMode>,
);

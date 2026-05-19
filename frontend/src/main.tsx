import { createRoot } from 'react-dom/client';

import { AppProviders } from './app/providers';
import './styles/tokens.css';
import './styles/index.css';
import './styles/file-browser-polish.css';

createRoot(document.getElementById('root') as HTMLElement).render(<AppProviders />);

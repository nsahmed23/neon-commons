import './style.css';
import { App } from './core/App';

const root = document.getElementById('app');
if (!root) throw new Error('Missing #app container');

const app = new App(root);
app.start();

// Dev/audit handle: lets scripted browser sessions (self-repair loop,
// Stage G audit) inspect and drive the app without brittle UI walking.
(window as unknown as { __neonApp: App }).__neonApp = app;

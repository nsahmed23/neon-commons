import './style.css';
import { App } from './core/App';

const root = document.getElementById('app');
if (!root) throw new Error('Missing #app container');

const app = new App(root);
app.start();

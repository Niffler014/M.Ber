import '@testing-library/jest-dom';
import { vi } from 'vitest';

// jsdom mock for scrollIntoView
window.HTMLElement.prototype.scrollIntoView = vi.fn();

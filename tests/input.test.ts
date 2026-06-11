/**
 * Regression tests for the Stage G live-audit defect: typing a board
 * share code into the intro textbox was swallowed by the game
 * keybindings (preventDefault on W/A/S/D/R/E/N/M/P/B/F/Space) AND
 * fired their actions — typing "NCBW" produced "C" while toggling
 * day-night and race debug in the background. Key events that target
 * editable elements must be ignored by every game key path.
 */

import { describe, expect, test } from 'vitest';
import { isEditableTarget } from '../src/core/Input';

describe('isEditableTarget', () => {
  test('returns true for text-entry tags', () => {
    expect(isEditableTarget({ tagName: 'INPUT' })).toBe(true);
    expect(isEditableTarget({ tagName: 'TEXTAREA' })).toBe(true);
    expect(isEditableTarget({ tagName: 'SELECT' })).toBe(true);
  });

  test('returns true for contenteditable regions regardless of tag', () => {
    expect(isEditableTarget({ tagName: 'DIV', isContentEditable: true })).toBe(true);
  });

  test('returns false for ordinary page elements', () => {
    expect(isEditableTarget({ tagName: 'DIV' })).toBe(false);
    expect(isEditableTarget({ tagName: 'BODY' })).toBe(false);
    expect(isEditableTarget({ tagName: 'CANVAS' })).toBe(false);
    expect(isEditableTarget({ tagName: 'BUTTON' })).toBe(false);
  });

  test('returns false for null targets (window-level key events)', () => {
    expect(isEditableTarget(null)).toBe(false);
  });

  test('isContentEditable=false does not mask a real input tag', () => {
    expect(isEditableTarget({ tagName: 'INPUT', isContentEditable: false })).toBe(true);
  });
});

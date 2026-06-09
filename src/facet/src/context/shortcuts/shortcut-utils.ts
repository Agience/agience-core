import type { ShortcutCombo } from './types';

const MAC_PLATFORM_REGEX = /(Mac|iPhone|iPad|iPod)/i;

export interface ParsedCombo {
  key?: string;
  alt: boolean;
  shift: boolean;
  ctrl: boolean;
  meta: boolean;
  mod: boolean;
}

export function isMacPlatform(): boolean {
  if (typeof navigator === 'undefined' || typeof navigator.platform !== 'string') {
    return false;
  }
  return MAC_PLATFORM_REGEX.test(navigator.platform);
}

export function normalizeCombo(combo: string): string {
  return combo
    .split('+')
    .map((part) => part.trim().toLowerCase())
    .filter(Boolean)
    .join('+');
}

export function parseCombo(rawCombo: string): ParsedCombo {
  const combo = normalizeCombo(rawCombo);
  const parts = combo.split('+');
  const parsed: ParsedCombo = {
    key: undefined,
    alt: false,
    shift: false,
    ctrl: false,
    meta: false,
    mod: false,
  };

  for (const part of parts) {
    switch (part) {
      case 'mod':
        parsed.mod = true;
        break;
      case 'ctrl':
      case 'control':
        parsed.ctrl = true;
        break;
      case 'cmd':
      case 'command':
      case 'meta':
        parsed.meta = true;
        break;
      case 'alt':
      case 'option':
        parsed.alt = true;
        break;
      case 'shift':
        parsed.shift = true;
        break;
      case 'enter':
      case 'return':
        parsed.key = 'enter';
        break;
      case 'space':
      case 'spacebar':
        parsed.key = ' ';
        break;
      default:
        parsed.key = part;
        break;
    }
  }

  return parsed;
}

export function keyMatches(eventKey: string, expectedKey?: string): boolean {
  if (!expectedKey) return true;
  const key = eventKey.length === 1 ? eventKey.toLowerCase() : eventKey.toLowerCase();

  if (expectedKey.length === 1) {
    return key === expectedKey;
  }

  switch (expectedKey) {
    case 'enter':
      return key === 'enter' || key === 'return';
    default:
      return key === expectedKey;
  }
}

export function matchesParsedCombo(event: KeyboardEvent, parsed: ParsedCombo, mac: boolean): boolean {
  if (parsed.mod) {
    if (mac) {
      if (!event.metaKey) return false;
    } else if (!event.ctrlKey) {
      return false;
    }
  }

  if (parsed.ctrl && !event.ctrlKey) return false;
  if (parsed.meta && !event.metaKey) return false;
  if (parsed.alt && !event.altKey) return false;
  if (parsed.shift && !event.shiftKey) return false;

  if (parsed.key) {
    return keyMatches(event.key, parsed.key);
  }

  return true;
}

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!target || !(target instanceof Element)) return false;
  const element = target as HTMLElement;
  const tagName = element.tagName?.toLowerCase();
  const isContentEditable = Boolean(element.isContentEditable);
  return (
    isContentEditable ||
    tagName === 'input' ||
    tagName === 'textarea' ||
    element.getAttribute('role') === 'textbox'
  );
}

export function formatShortcutCombo(combo: ShortcutCombo): string[] {
  const mac = isMacPlatform();
  const normalized = normalizeCombo(combo);
  const parts = normalized.split('+');
  const formatted: string[] = [];

  for (const part of parts) {
    switch (part) {
      case 'mod':
        formatted.push(mac ? '⌘' : 'Ctrl');
        break;
      case 'ctrl':
      case 'control':
        formatted.push('Ctrl');
        break;
      case 'cmd':
      case 'command':
      case 'meta':
        formatted.push('⌘');
        break;
      case 'alt':
      case 'option':
        formatted.push(mac ? '⌥' : 'Alt');
        break;
      case 'shift':
        formatted.push('Shift');
        break;
      case 'space':
      case 'spacebar':
        formatted.push('Space');
        break;
      default: {
        if (part.length === 1) {
          formatted.push(part.toUpperCase());
        } else {
          formatted.push(part.replace(/-/g, ' '));
        }
        break;
      }
    }
  }

  return formatted;
}

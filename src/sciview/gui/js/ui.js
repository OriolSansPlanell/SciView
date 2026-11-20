// Small DOM helpers: element builder, toasts, modals, popovers.
import { icon } from './icons.js';

export function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else if (k === 'html') e.innerHTML = v;
    else if (k === 'dataset') Object.assign(e.dataset, v);
    else if (v === true) e.setAttribute(k, '');
    else e.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    e.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return e;
}

export function iconEl(name, cls = '') {
  const span = el('span', { class: cls });
  span.innerHTML = icon(name);
  return span;
}

export function toast(msg, kind = '') {
  const root = document.getElementById('toasts');
  const t = el('div', { class: `toast ${kind}`, role: kind === 'err' ? 'alert' : 'status' }, msg);
  root.append(t);
  setTimeout(() => t.remove(), kind === 'err' ? 6000 : 2600);
}

export function fmtTime(t) {
  return (Math.round(t * 100) / 100).toFixed(2);
}

export function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

export function round(v, step) {
  if (!step) return v;
  const dec = Math.max(0, -Math.floor(Math.log10(step) + 1e-9) + 1);
  return Number((Math.round(v / step) * step).toFixed(Math.min(6, dec)));
}

// ------------------------------------------------------------------ modals
let modalStack = [];

export function openModal({ title, body, footer, wide = false, onClose, dismissable = true }) {
  const root = document.getElementById('modalRoot');
  const close = () => {
    backdrop.remove();
    modalStack = modalStack.filter((m) => m !== close);
    document.removeEventListener('keydown', onKey, true);
    if (onClose) onClose();
  };
  const onKey = (e) => {
    if (e.key === 'Escape' && dismissable && modalStack[modalStack.length - 1] === close) {
      e.stopPropagation();
      close();
    }
  };
  const closeBtn = dismissable ? el('button', { class: 'icon-btn', title: 'Close', 'aria-label': 'Close', onclick: close, html: icon('close') }) : null;
  const modal = el('div', { class: `modal ${wide ? 'wide' : ''}`, role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
    el('header', {}, el('h2', {}, title), closeBtn),
    el('div', { class: 'body' }, body),
    footer ? el('footer', {}, footer) : null);
  const backdrop = el('div', { class: 'modal-backdrop', onmousedown: (e) => { if (e.target === backdrop && dismissable) close(); } }, modal);
  root.append(backdrop);
  modalStack.push(close);
  document.addEventListener('keydown', onKey, true);
  setTimeout(() => { const f = modal.querySelector('input, select, button.primary'); if (f) f.focus(); }, 30);
  return close;
}

export const modalOpen = () => modalStack.length > 0;

// ------------------------------------------------------------------ popover
let activePop = null;
export function popover(anchor, content) {
  closePopover();
  const r = anchor.getBoundingClientRect();
  const pop = el('div', { class: 'popover' }, content);
  document.body.append(pop);
  const pw = pop.offsetWidth, ph = pop.offsetHeight;
  let x = r.left, y = r.bottom + 6;
  if (x + pw > window.innerWidth - 8) x = window.innerWidth - pw - 8;
  if (y + ph > window.innerHeight - 8) y = r.top - ph - 6;
  pop.style.left = `${Math.max(8, x)}px`;
  pop.style.top = `${Math.max(8, y)}px`;
  const away = (e) => { if (!pop.contains(e.target) && e.target !== anchor) closePopover(); };
  setTimeout(() => document.addEventListener('mousedown', away), 0);
  activePop = { pop, away };
  return pop;
}
export function closePopover() {
  if (!activePop) return;
  document.removeEventListener('mousedown', activePop.away);
  activePop.pop.remove();
  activePop = null;
}

/** Drag helper: calls move(dx, dy, ev) while dragging, end(moved) on release. */
export function drag(ev, move, end) {
  const x0 = ev.clientX, y0 = ev.clientY;
  let moved = false;
  const mm = (e) => {
    const dx = e.clientX - x0, dy = e.clientY - y0;
    if (!moved && Math.abs(dx) + Math.abs(dy) < 3) return;
    moved = true;
    move(dx, dy, e);
  };
  const mu = (e) => {
    window.removeEventListener('pointermove', mm);
    window.removeEventListener('pointerup', mu);
    if (end) end(moved, e);
  };
  window.addEventListener('pointermove', mm);
  window.addEventListener('pointerup', mu);
}

// picture.js: a picture of this window for a beta note (the classic betaNotes.ts picture), drawn by html-to-image
// (the classic page's own package at the same version). The note's dialog is left out of it.
import { toPng } from "html-to-image";

export async function picture(skipSelector) {
  const skip = [...document.querySelectorAll(skipSelector)];
  return toPng(document.body, {
    width: window.innerWidth,
    height: window.innerHeight,
    pixelRatio: 1,
    cacheBust: false,
    backgroundColor: getComputedStyle(document.body).backgroundColor,
    filter: (node) => !(node instanceof Element) || !skip.some((s) => s === node),
  });
}

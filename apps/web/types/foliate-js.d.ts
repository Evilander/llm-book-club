declare module "foliate-js/view.js" {
  export class View extends HTMLElement {}
}

declare module "foliate-js/overlayer.js" {
  export class Overlayer {
    static highlight(
      rects: Array<Record<string, number>>,
      options?: { color?: string; padding?: number },
    ): SVGElement;
  }
}

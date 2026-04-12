/// <reference types="vite/client" />

declare const __APP_VERSION__: string;
declare const __APP_BUILD_TIME__: string;
declare const __APP_GIT_SHA__: string;

type AgienceRuntimeConfig = {
  backendUri?: string;
  clientId?: string;
  title?: string;
  favicon?: string;
};

interface Window {
  __AGIENCE_CONFIG__?: AgienceRuntimeConfig;
}

declare module '*.svg' {
  import * as React from 'react';
  export const ReactComponent: React.FunctionComponent<
    React.SVGProps<SVGSVGElement> & { title?: string }
  >;
  const src: string;
  export default src;
}

declare module '*.svg?react' {
  import * as React from 'react';
  const ReactComponent: React.FunctionComponent<
    React.SVGProps<SVGSVGElement> & { title?: string }
  >;
  export default ReactComponent;
}

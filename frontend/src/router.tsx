import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { createIsomorphicFn } from "@tanstack/react-start";
import { routeTree } from "./routeTree.gen";

const getSsrOptions = createIsomorphicFn().server(() => {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return { nonce: Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("") };
});

export const getRouter = () => {
  const queryClient = new QueryClient();

  const router = createRouter({
    routeTree,
    ssr: getSsrOptions(),
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return router;
};

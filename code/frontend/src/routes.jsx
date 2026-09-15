import App from "./App.jsx";
import Result from "./pages/Result.jsx";
import Trending from "./pages/Trending.jsx";
import Knowledge from "./pages/Knowledge.jsx";
import Bot from "./pages/Bot.jsx";
import OAuthCallback from "./pages/OAuthCallback.jsx";
import NotFound from "./pages/NotFound.jsx";
// handle.topbar: "brand" | "back" — read by the app shell (P-14).
// "/" temporarily mounts the legacy App until S-02 replaces it with the new home page.
export const routes = [
  { path: "/", element: <App />, handle: { topbar: "brand" } },
  { path: "/r/:id", element: <Result />, handle: { topbar: "back" } },
  { path: "/trending", element: <Trending />, handle: { topbar: "brand" } },
  { path: "/knowledge", element: <Knowledge />, handle: { topbar: "brand" } },
  { path: "/bot", element: <Bot />, handle: { topbar: "back" } },
  { path: "/oauth/callback", element: <OAuthCallback />, handle: { topbar: "brand" } },
  { path: "*", element: <NotFound />, handle: { topbar: "brand" } },
];

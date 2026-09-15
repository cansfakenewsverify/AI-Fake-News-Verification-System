import AppShell from "./components/shell/AppShell.jsx";
import Home from "./pages/Home.jsx";
import Result from "./pages/Result.jsx";
import Trending from "./pages/Trending.jsx";
import Knowledge from "./pages/Knowledge.jsx";
import Bot from "./pages/Bot.jsx";
import OAuthCallback from "./pages/OAuthCallback.jsx";
import NotFound from "./pages/NotFound.jsx";
// All pages render inside the AppShell layout (P-14).
// handle.topbar: "brand" | "back" — mobile top bar variant.
// handle.tab: "home" | "trending" | "knowledge" | "bot" — current nav item (aria-current="page").
// "/" is the new home page (S-02 replaced the legacy App and removed the temporary "/new" route).
export const routes = [
  {
    element: <AppShell />,
    children: [
      { path: "/", element: <Home />, handle: { topbar: "brand", tab: "home" } },
      { path: "/r/:id", element: <Result />, handle: { topbar: "back", tab: "home" } },
      { path: "/trending", element: <Trending />, handle: { topbar: "brand", tab: "trending" } },
      { path: "/knowledge", element: <Knowledge />, handle: { topbar: "brand", tab: "knowledge" } },
      { path: "/bot", element: <Bot />, handle: { topbar: "back", tab: "bot" } },
      { path: "/oauth/callback", element: <OAuthCallback />, handle: { topbar: "brand" } },
      { path: "*", element: <NotFound />, handle: { topbar: "brand" } },
    ],
  },
];

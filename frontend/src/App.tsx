import { NavigationProvider, useNavigation } from "./navigation/NavigationContext";
import AppShell from "./components/layout/AppShell";
import DashboardPage from "./components/dashboard/DashboardPage";
import CompanyPage from "./components/company/CompanyPage";
import NewsPage from "./components/news/NewsPage";

function Routed() {
  const { route } = useNavigation();
  return (
    <AppShell>
      {route.name === "dashboard" && <DashboardPage />}
      {route.name === "news" && <NewsPage />}
      {route.name === "company" && <CompanyPage id={route.id} />}
    </AppShell>
  );
}

export default function App() {
  return (
    <NavigationProvider>
      <Routed />
    </NavigationProvider>
  );
}

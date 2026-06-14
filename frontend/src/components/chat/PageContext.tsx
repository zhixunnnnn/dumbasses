import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

export type AssistantPageContext = Record<string, unknown>;

type PageContextValue = {
  pageContext: AssistantPageContext;
  setPageContext: (context: AssistantPageContext) => void;
};

const AssistantPageContextContext = createContext<PageContextValue | null>(null);

export function AssistantPageContextProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [pageContext, setPageContext] = useState<AssistantPageContext>({
    route: "dashboard",
    title: "Sustainability Matrix",
  });

  const value = useMemo(
    () => ({ pageContext, setPageContext }),
    [pageContext],
  );

  return (
    <AssistantPageContextContext.Provider value={value}>
      {children}
    </AssistantPageContextContext.Provider>
  );
}

export function useAssistantPageContext() {
  const ctx = useContext(AssistantPageContextContext);
  if (!ctx) {
    throw new Error(
      "useAssistantPageContext must be used within AssistantPageContextProvider",
    );
  }
  return ctx.pageContext;
}

export function usePublishAssistantPageContext(
  pageContext: AssistantPageContext,
) {
  const ctx = useContext(AssistantPageContextContext);
  if (!ctx) {
    throw new Error(
      "usePublishAssistantPageContext must be used within AssistantPageContextProvider",
    );
  }
  const { setPageContext } = ctx;

  useEffect(() => {
    setPageContext(pageContext);
  }, [setPageContext, pageContext]);
}

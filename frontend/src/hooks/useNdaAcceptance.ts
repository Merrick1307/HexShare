import { useEffect, useMemo, useRef, useState } from "react";
import type { NdaStatus } from "../types";

export interface NdaGateProps {
  status: NdaStatus;
  onAccept: (payload: {
    typed_name: string;
    scroll_confirmed: boolean;
    checkbox_confirmed: boolean;
  }) => Promise<void>;
}

export function useNdaAcceptance({ status, onAccept }: NdaGateProps) {
  const policy = status.policy;
  const isPdf = policy?.content_type === "pdf";
  const requireScroll = Boolean(policy?.require_scroll) && !isPdf;
  const requireSignature = Boolean(policy?.require_typed_signature);

  const [scrolledToEnd, setScrolledToEnd] = useState(!requireScroll);
  const [typedName, setTypedName] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Short agreements that fit without a scrollbar can't produce a scroll event,
  // so treat non-scrollable content as already read.
  useEffect(() => {
    if (!requireScroll) {
      setScrolledToEnd(true);
      return;
    }
    const el = scrollRef.current;
    if (el && el.scrollHeight <= el.clientHeight + 4) {
      setScrolledToEnd(true);
    }
  }, [requireScroll, status.text_body]);

  const canAccept = useMemo(() => {
    if (!scrolledToEnd) return false;
    if (!agreed) return false;
    if (requireSignature && !typedName.trim()) return false;
    return true;
  }, [scrolledToEnd, agreed, requireSignature, typedName]);

  function handleScroll() {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 24) {
      setScrolledToEnd(true);
    }
  }

  async function handleAccept() {
    if (!canAccept || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await onAccept({
        typed_name: typedName.trim(),
        scroll_confirmed: scrolledToEnd,
        checkbox_confirmed: agreed,
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to record acceptance.",
      );
      setSubmitting(false);
    }
  }

  return {
    policy,
    isPdf,
    requireScroll,
    requireSignature,
    scrolledToEnd,
    typedName,
    setTypedName,
    agreed,
    setAgreed,
    submitting,
    error,
    scrollRef,
    canAccept,
    handleScroll,
    handleAccept,
  };
}

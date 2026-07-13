import { useCallback, useEffect, useRef, useState } from 'react';
import { message } from 'antd';
import type { User, WechatPollStatus, WechatQrcodeResponse } from '../../types';

export interface WechatQrPollResult {
  status: WechatPollStatus;
  user?: User;
  step?: number;
}

export type WechatQrPollHandlerResult =
  | 'continue'
  | 'stop'
  | { action: 'continue' | 'stop'; hint?: string };

interface UseWechatQrcodePollOptions {
  active: boolean;
  fetchQrcode: () => Promise<WechatQrcodeResponse>;
  pollStatus: (state: string) => Promise<WechatQrPollResult>;
  onPoll: (result: WechatQrPollResult) => WechatQrPollHandlerResult;
  onLoaded?: (data: WechatQrcodeResponse) => string | undefined;
}

export function useWechatQrcodePoll({
  active,
  fetchQrcode,
  pollStatus,
  onPoll,
  onLoaded,
}: UseWechatQrcodePollOptions) {
  const [loading, setLoading] = useState(false);
  const [qrcode, setQrcode] = useState<WechatQrcodeResponse | null>(null);
  const [hint, setHint] = useState('');
  const pollTimerRef = useRef<number | null>(null);
  const onPollRef = useRef(onPoll);
  const onLoadedRef = useRef(onLoaded);

  onPollRef.current = onPoll;
  onLoadedRef.current = onLoaded;

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current !== null) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const resolvePoll = useCallback(
    (result: WechatQrPollResult) => {
      const outcome = onPollRef.current(result);
      const action = typeof outcome === 'string' ? outcome : outcome.action;
      const nextHint = typeof outcome === 'string' ? undefined : outcome.hint;
      if (nextHint !== undefined) {
        setHint(nextHint);
      }
      if (action === 'stop') {
        stopPolling();
      }
    },
    [stopPolling],
  );

  const startPolling = useCallback(
    (state: string) => {
      stopPolling();
      pollTimerRef.current = window.setInterval(async () => {
        try {
          resolvePoll(await pollStatus(state));
        } catch {
          stopPolling();
        }
      }, 2000);
    },
    [pollStatus, resolvePoll, stopPolling],
  );

  const loadQrcode = useCallback(async () => {
    setLoading(true);
    stopPolling();
    setHint('');
    try {
      const data = await fetchQrcode();
      setQrcode(data);
      const initialHint = onLoadedRef.current?.(data);
      if (initialHint) {
        setHint(initialHint);
      }
      startPolling(data.state);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '获取二维码失败');
      setQrcode(null);
    } finally {
      setLoading(false);
    }
  }, [fetchQrcode, startPolling, stopPolling]);

  useEffect(() => {
    if (active) {
      void loadQrcode();
    } else {
      stopPolling();
      setQrcode(null);
      setHint('');
    }
    return () => stopPolling();
  }, [active, loadQrcode, stopPolling]);

  return { loading, qrcode, hint, loadQrcode };
}

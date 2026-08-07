import { useState, useEffect } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { apiClient } from '../services/apiClient';

interface ApiStatusBadgeProps {
  onRetry?: () => void;
  externalStatus?: 'ok' | 'fail' | 'loading';
  latencyMs?: number;
}

export default function ApiStatusBadge({ onRetry, externalStatus, latencyMs = 0 }: ApiStatusBadgeProps) {
  const [status, setStatus] = useState<'ok' | 'fail' | 'loading'>(externalStatus || 'loading');
  const [latency, setLatency] = useState<number>(latencyMs);
  const [retryCountdown, setRetryCountdown] = useState<number>(0);

  const checkHealth = async () => {
    setStatus('loading');
    const res = await apiClient.getSystemHealth();
    if (res.status === 'ok' && res.data) {
      setStatus('ok');
      setLatency(res.latencyMs);
      setRetryCountdown(0);
    } else {
      setStatus('fail');
      setLatency(0);
      setRetryCountdown(5);
    }
  };

  useEffect(() => {
    if (externalStatus) {
      setStatus(externalStatus);
      setLatency(latencyMs);
      if (externalStatus === 'fail' && retryCountdown === 0) {
        setRetryCountdown(5);
      }
    } else {
      checkHealth();
    }
  }, [externalStatus, latencyMs]);

  // Auto-countdown when API fails
  useEffect(() => {
    if (status !== 'fail' || retryCountdown <= 0) return;
    const timer = setInterval(() => {
      setRetryCountdown((prev) => {
        if (prev <= 1) {
          if (onRetry) onRetry();
          else checkHealth();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [status, retryCountdown, onRetry]);

  if (status === 'loading') {
    return (
      <div className="flex items-center gap-1.5 px-3 py-1 bg-slate-800/80 border border-slate-700/60 rounded-full text-xs font-medium text-slate-300 shadow-sm animate-pulse">
        <RefreshCw className="w-3.5 h-3.5 animate-spin text-sky-400" />
        <span>Connecting API...</span>
      </div>
    );
  }

  if (status === 'ok') {
    return (
      <div 
        onClick={checkHealth}
        title="API Server is Online and P50/P95 Latency SLA is met. Click to ping."
        className="cursor-pointer flex items-center gap-1.5 px-3 py-1 bg-emerald-950/60 border border-emerald-500/30 hover:border-emerald-500/60 rounded-full text-xs font-semibold text-emerald-300 shadow-sm transition-all duration-200"
      >
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
        <span className="w-2 h-2 rounded-full bg-emerald-400 -ml-3.5" />
        <span>🟢 API OK</span>
        <span className="text-emerald-400/80 font-mono text-[11px] bg-emerald-900/40 px-1.5 py-0.2 rounded">
          {latency}ms
        </span>
      </div>
    );
  }

  return (
    <div 
      onClick={() => { setRetryCountdown(0); if (onRetry) onRetry(); else checkHealth(); }}
      title="FastAPI connection offline or timed out. Click to retry now."
      className="cursor-pointer flex items-center gap-1.5 px-3 py-1 bg-rose-950/80 border border-rose-500/40 hover:border-rose-500/70 rounded-full text-xs font-semibold text-rose-300 shadow-sm transition-all duration-200 animate-bounce"
    >
      <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
      <span>🔴 API FAIL</span>
      {retryCountdown > 0 ? (
        <span className="text-rose-200/90 font-mono text-[11px] bg-rose-900/60 px-1.5 py-0.2 rounded">
          Auto retry in {retryCountdown}s...
        </span>
      ) : (
        <span className="text-rose-200/90 text-[11px] underline">Click to retry</span>
      )}
    </div>
  );
}

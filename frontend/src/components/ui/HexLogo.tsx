import React from 'react';
import { cn } from '../../lib/utils';

export function HexLogo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn('h-8 w-8', className)}
    >
      {/* Outer Hexagon Track - Subtle structural guide */}
      <path
        d="M50 5L88.9711 27.5V72.5L50 95L11.0289 72.5V27.5L50 5Z"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-zinc-200"
      />
      
      {/* Inner Hexagon Track - Bold, anchoring shape */}
      <path
        d="M50 20L75.9808 35V65L50 80L24.0192 65V35L50 20Z"
        stroke="currentColor"
        strokeWidth="6"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-zinc-950"
      />

      {/* Data Nodes / Movement Indicators - Indigo to match the badge/buttons */}
      <circle cx="50" cy="5" r="6" className="fill-indigo-600 animate-[spin_4s_linear_infinite]" style={{ transformOrigin: '50px 50px' }} />
      <circle cx="88.9711" cy="72.5" r="5" className="fill-indigo-500 animate-[spin_4s_linear_infinite_reverse]" style={{ transformOrigin: '50px 50px' }} />
      <circle cx="24.0192" cy="65" r="4" className="fill-indigo-600 animate-[spin_3s_linear_infinite]" style={{ transformOrigin: '50px 50px' }} />
      
      {/* Center Core - Solid anchor */}
      <circle cx="50" cy="50" r="10" className="fill-zinc-950" />
    </svg>
  );
}

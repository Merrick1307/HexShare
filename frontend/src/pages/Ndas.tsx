// import { useEffect, useState } from 'react';
// import { Link } from 'react-router-dom';
// import { format } from 'date-fns';
// import { FileText, FolderOpen, ShieldCheck } from 'lucide-react';
// import { api } from '../services/api';
// import { NdaPolicySummary } from '../types';
// import { Badge } from '../components/ui/Badge';
//
// export function Ndas() {
//   const [policies, setPolicies] = useState<NdaPolicySummary[] | null>(null);
//   const [error, setError] = useState<string | null>(null);
//
//   useEffect(() => {
//     let cancelled = false;
//     api
//       .listNdaPolicies()
//       .then((data) => !cancelled && setPolicies(data))
//       .catch((err) => !cancelled && setError(err instanceof Error ? err.message : 'Failed to load NDAs'));
//     return () => {
//       cancelled = true;
//     };
//   }, []);
//
//   return (
//     <div className="space-y-8">
//       <div>
//         <h1 className="text-2xl font-semibold tracking-tight text-zinc-950">NDAs</h1>
//         <p className="mt-1 text-sm text-zinc-500">
//           Which documents and rooms are NDA-gated, and how many recipients have signed the current version.
//           Set or edit an NDA from a document or room.
//         </p>
//       </div>
//
//       {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}
//
//       <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm">
//         <table className="w-full text-left text-sm">
//           <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase text-zinc-500">
//             <tr>
//               <th className="px-6 py-3">Scope</th>
//               <th className="px-6 py-3">Type</th>
//               <th className="px-6 py-3">Version</th>
//               <th className="px-6 py-3">Signatures</th>
//               <th className="px-6 py-3">Updated</th>
//             </tr>
//           </thead>
//           <tbody className="divide-y divide-zinc-100">
//             {policies === null ? (
//               <tr><td colSpan={5} className="px-6 py-10 text-center text-zinc-500">Loading NDAs…</td></tr>
//             ) : policies.length === 0 ? (
//               <tr>
//                 <td colSpan={5} className="px-6 py-14 text-center text-zinc-500">
//                   <ShieldCheck className="mx-auto mb-3 h-8 w-8 text-zinc-300" />
//                   No NDAs configured. Open a document or a room to require one.
//                 </td>
//               </tr>
//             ) : (
//               policies.map((policy) => {
//                 const isRoom = policy.scope_type === 'room';
//                 const href = isRoom ? `/groups/${policy.scope_id}` : `/documents/${policy.scope_id}`;
//                 return (
//                   <tr key={`${policy.scope_type}:${policy.scope_id}`} className="hover:bg-zinc-50">
//                     <td className="px-6 py-4">
//                       <Link to={href} className="flex items-center gap-2 font-medium text-zinc-900 hover:text-indigo-600">
//                         {isRoom ? <FolderOpen className="h-4 w-4 text-zinc-400" /> : <FileText className="h-4 w-4 text-zinc-400" />}
//                         {policy.scope_name || policy.scope_id}
//                       </Link>
//                       {policy.title ? <p className="mt-0.5 text-xs text-zinc-500">{policy.title}</p> : null}
//                     </td>
//                     <td className="px-6 py-4">
//                       <Badge variant="neutral">{policy.content_type === 'pdf' ? 'PDF' : 'Text'}</Badge>
//                     </td>
//                     <td className="px-6 py-4 text-zinc-600">v{policy.version}</td>
//                     <td className="px-6 py-4">
//                       <Badge variant={policy.acceptance_count > 0 ? 'success' : 'neutral'}>
//                         {policy.acceptance_count} signed
//                       </Badge>
//                     </td>
//                     <td className="px-6 py-4 text-zinc-500">{format(new Date(policy.updated_at), 'MMM d, yyyy')}</td>
//                   </tr>
//                 );
//               })
//             )}
//           </tbody>
//         </table>
//       </div>
//     </div>
//   );
// }


import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { format } from "date-fns";
import { FileText, FolderOpen, ShieldCheck } from "lucide-react";
import { api } from "../services/api";
import { NdaPolicySummary } from "../types";
import { Badge } from "../components/ui/Badge";

export function Ndas() {
  const [policies, setPolicies] = useState<NdaPolicySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listNdaPolicies()
      .then((data) => !cancelled && setPolicies(data))
      .catch(
        (err) =>
          !cancelled &&
          setError(err instanceof Error ? err.message : "Failed to load NDAs"),
      );
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-8 text-foreground">
      <div>
        <p className="text-primary text-xs font-semibold uppercase tracking-[0.18em]">
          Agreements and acceptance
        </p>
        <h1 className="text-foreground mt-2 text-2xl font-semibold tracking-tight">
          NDAs
        </h1>
        <p className="text-muted-foreground mt-2 max-w-3xl text-sm leading-relaxed">
          Which documents and rooms are NDA-gated, and how many recipients have
          signed the current version. Set or edit an NDA from a document or
          room.
        </p>
      </div>

      {error ? (
        <div className="border-destructive/20 bg-destructive/10 text-destructive rounded-xl border px-4 py-3 text-sm">
          {error}
        </div>
      ) : null}

      <div className="border-border bg-card text-card-foreground overflow-x-auto rounded-xl border shadow-sm">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-border bg-muted/60 text-muted-foreground border-b text-xs font-semibold uppercase tracking-[0.08em]">
            <tr>
              <th className="px-6 py-3">Scope</th>
              <th className="px-6 py-3">Type</th>
              <th className="px-6 py-3">Version</th>
              <th className="px-6 py-3">Signatures</th>
              <th className="px-6 py-3">Updated</th>
            </tr>
          </thead>
          <tbody className="divide-border divide-y">
            {policies === null ? (
              <tr>
                <td
                  colSpan={5}
                  className="text-muted-foreground px-6 py-10 text-center"
                >
                  Loading NDAs…
                </td>
              </tr>
            ) : policies.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  className="text-muted-foreground px-6 py-14 text-center"
                >
                  <ShieldCheck className="text-primary mx-auto mb-3 h-8 w-8" />
                  No NDAs configured. Open a document or a room to require one.
                </td>
              </tr>
            ) : (
              policies.map((policy) => {
                const isRoom = policy.scope_type === "room";
                const href = isRoom
                  ? `/groups/${policy.scope_id}`
                  : `/documents/${policy.scope_id}`;
                return (
                  <tr
                    key={`${policy.scope_type}:${policy.scope_id}`}
                    className="hover:bg-muted/60 transition-colors"
                  >
                    <td className="px-6 py-4">
                      <Link
                        to={href}
                        className="text-foreground hover:text-primary flex items-center gap-2 font-medium"
                      >
                        {isRoom ? (
                          <FolderOpen className="text-primary h-4 w-4" />
                        ) : (
                          <FileText className="text-primary h-4 w-4" />
                        )}
                        {policy.scope_name || policy.scope_id}
                      </Link>
                      {policy.title ? (
                        <p className="text-muted-foreground mt-0.5 text-xs">
                          {policy.title}
                        </p>
                      ) : null}
                    </td>
                    <td className="px-6 py-4">
                      <Badge variant="neutral">
                        {policy.content_type === "pdf" ? "PDF" : "Text"}
                      </Badge>
                    </td>
                    <td className="text-muted-foreground px-6 py-4">
                      v{policy.version}
                    </td>
                    <td className="px-6 py-4">
                      <Badge
                        variant={
                          policy.acceptance_count > 0 ? "success" : "neutral"
                        }
                      >
                        {policy.acceptance_count} signed
                      </Badge>
                    </td>
                    <td className="text-muted-foreground px-6 py-4">
                      {format(new Date(policy.updated_at), "MMM d, yyyy")}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
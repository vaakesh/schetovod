import type { Issue } from "../types";

interface Props {
  issues: Issue[];
  // the issues are about the saved form, not the edits since
  stale: boolean;
}

export function IssueItem({ issue }: { issue: Issue }) {
  return (
    <div className={issue.blocking ? "issue issue-blocking" : "issue issue-warning"}>
      {issue.message}
    </div>
  );
}

export default function IssuesList({ issues, stale }: Props) {
  if (issues.length === 0) {
    return null;
  }
  // what blocks the posting goes first
  const sorted = [...issues].sort((a, b) => Number(b.blocking) - Number(a.blocking));
  return (
    <section className={stale ? "issues stale" : "issues"}>
      {sorted.map((issue, index) => (
        <IssueItem key={index} issue={issue} />
      ))}
    </section>
  );
}

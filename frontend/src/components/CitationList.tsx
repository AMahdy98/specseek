import type { Citation } from '../api'

interface Props {
  citations: Citation[]
  refused: boolean
}

/** The stored heading starts with its own clause number ("4.2 Safety-Critical…"). For clause
 *  4.2 that would print the number twice; for 3.7.3 it is the parent section "3.7 …". */
export function headingLabel({ clause_id, heading }: Pick<Citation, 'clause_id' | 'heading'>) {
  if (!heading) return ''
  if (clause_id && heading.startsWith(`${clause_id} `)) return heading.slice(clause_id.length + 1)
  return clause_id ? `(in ${heading})` : heading
}

export function CitationList({ citations, refused }: Props) {
  if (citations.length === 0) return null
  return (
    <>
      <h2>{refused ? 'Passages searched' : 'Sources given to the model'}</h2>
      <ol className="citations">
        {citations.map((citation, index) => (
          // Index as key is acceptable here: the list is replaced as a whole, never reordered.
          <li key={index}>
            <div className="citation-head">
              <strong>{citation.clause_id ?? 'No clause number'}</strong>
              <span> {headingLabel(citation)}</span>
            </div>
            <div className="citation-meta">
              {citation.document} · page {citation.page} · similarity {citation.score.toFixed(2)}
            </div>
            <p className="snippet">{citation.snippet}…</p>
          </li>
        ))}
      </ol>
    </>
  )
}

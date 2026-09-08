export interface DiffWord {
  text: string;
  // the word is not in the other name
  changed: boolean;
}

// the same normalization as the backend uses for names, enough to compare words
function wordKey(word: string): string {
  return word.toLowerCase().replaceAll("ё", "е").replace(/["'«»“”„`]/g, "");
}

// the words of the candidate name, marked where they differ from the line name
export function wordDiff(line: string, candidate: string): DiffWord[] {
  const a = line.split(/\s+/).filter(Boolean).map(wordKey);
  const words = candidate.split(/\s+/).filter(Boolean);
  const b = words.map(wordKey);
  // longest common subsequence of words, the table is filled from the end
  const common: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  );
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      common[i]![j] =
        a[i] === b[j]
          ? common[i + 1]![j + 1]! + 1
          : Math.max(common[i + 1]![j]!, common[i]![j + 1]!);
    }
  }
  const kept = new Set<number>();
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      kept.add(j);
      i++;
      j++;
    } else if (common[i + 1]![j]! >= common[i]![j + 1]!) {
      i++;
    } else {
      j++;
    }
  }
  return words.map((text, index) => ({ text, changed: !kept.has(index) }));
}

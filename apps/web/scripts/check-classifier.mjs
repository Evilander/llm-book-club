#!/usr/bin/env node
// Regression guard for the after-dark folder classifier.
// Run with: npx tsx scripts/check-classifier.mjs
//
// Critical safety: the classifier MUST NOT pull children's / young-adult
// folders into the 18+ portal. We had this exact bug in the first cut
// because "young adult".includes("adult") is true.
import { classifyFolder } from "../lib/after-dark.ts";

const cases = [
  { folder: "Children's & Young Adult", expect: false, why: "YA must not match 'adult'" },
  { folder: "Young Adult", expect: false, why: "YA must not match 'adult'" },
  { folder: "Adult Fiction", expect: true, why: "true adult shelf" },
  { folder: "Erotica", expect: true, why: "obvious adult" },
  { folder: "Erotic Romance", expect: true, why: "obvious adult" },
  { folder: "Sex Education", expect: false, why: "education not erotica" },
  { folder: "Wessex Tales", expect: false, why: "must not match 'sex' substring in 'Wessex'" },
  { folder: "Sextant Manuals", expect: false, why: "must not match 'sex' substring" },
  { folder: "BDSM", expect: true, why: "obvious adult" },
  { folder: "Picture Books", expect: false, why: "kids" },
  { folder: "Juvenile Fiction", expect: false, why: "kids" },
  { folder: "Marquis de Sade", expect: true, why: "author indicator" },
  { folder: "Lesbian Poetry", expect: false, why: "safe override" },
  { folder: "Lesbian eBook Archive", expect: true, why: "explicit archive marker" },
  { folder: "After Dark", expect: true, why: "literal" },
  { folder: "Adventure", expect: false, why: "must not match anywhere" },
  { folder: "Sexuality Studies", expect: false, why: "studies are academic" },
  { folder: "History of Sex", expect: false, why: "history safe-listed" },
  { folder: "Children's Picture Books", expect: false, why: "kids" },
  { folder: "Middle Grade Adventure", expect: false, why: "middle grade is not adult" },
];

let pass = 0;
let fail = 0;
for (const c of cases) {
  const got = classifyFolder(c.folder).isAfterDark;
  const ok = got === c.expect;
  if (ok) {
    pass++;
    console.log(`  ok    ${c.folder.padEnd(34)} -> ${got}`);
  } else {
    fail++;
    console.log(`  FAIL  ${c.folder.padEnd(34)} -> got ${got}, expected ${c.expect}  (${c.why})`);
  }
}
console.log(`\n${pass}/${pass + fail} passed`);
process.exit(fail === 0 ? 0 : 1);

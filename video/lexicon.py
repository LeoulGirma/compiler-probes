"""Pronunciation lexicon for the narration.

The voice (Kokoro-82M) turns text into phonemes with espeak-ng before speaking. espeak guesses
acronyms and product names, and several guesses are wrong for a developer audience (it reads
"AOT" as "ay-ot", "Redis" as "ruh-DEEZ", "C#" as "see hash"). Each entry below pins one term to
exact phonemes, so the voice says it the way .NET developers do. Phonemes use Kokoro's IPA set:
ˈ marks primary stress, ˌ secondary stress.

Entries are matched longest first, case-sensitively, on word boundaries.
"""

# term as written in the script, how a reader should hear it, phonemes, why it is pinned
LEXICON = [
    ('Native AOT', 'NAY-tiv ay-oh-TEE', 'nˈeɪɾɪv ˌeɪˌoʊtˈiː', 'espeak reads "AOT" as one word, "ay-ot"'),
    ('NativeAOT', 'NAY-tiv ay-oh-TEE', 'nˈeɪɾɪv ˌeɪˌoʊtˈiː', 'same term, written as one word'),
    ('AOT', 'ay-oh-TEE', 'ˌeɪˌoʊtˈiː', 'spelled out, as in "ahead of time"'),
    ('C#', 'see SHARP', 'sˈiː ʃˈɑːɹp', 'espeak says "see hash"'),
    ('.NET', 'dot NET', 'dˈɑːt nˈɛt', 'the leading dot is otherwise dropped'),
    ('JIT', 'JIT (one word)', 'dʒˈɪt', 'said as a word, the way the runtime team says it'),
    ('LLVM', 'ell-ell-vee-EM', 'ˌɛlˌɛlvˌiːˈɛm', 'letters'),
    ('SIMD', 'SIM-dee', 'sˈɪmdˌiː', 'said as a word'),
    ('PGO', 'pee-jee-OH', 'pˌiːdʒˌiːˈoʊ', 'letters'),
    ('IL', 'eye-ELL', 'ˌaɪˈɛl', 'letters; espeak would say "ill"'),
    ('RC2', 'ar-see TWO', 'ˌɑːɹsˈiː tˈuː', 'release candidate 2'),
    ('JWT', 'jay-double-you-TEE', 'dʒˌeɪdˌʌbəljuːtˈiː', 'letters (some say "jot"; letters are clearer)'),
    ('Redis', 'RED-iss', 'ɹˈɛdɪs', 'espeak says "ruh-DEEZ"'),
    ('Postgres', 'POST-gress', 'pˈoʊstɡɹɛs', 'espeak says "POST-grers"'),
    ('async', 'AY-sink', 'ˈeɪsɪŋk', 'espeak says "uh-SINK"'),
    ('Async', 'AY-sink', 'ˈeɪsɪŋk', 'same, at the start of a sentence'),
    ('Vector of T', 'VEC-tor of TEE', 'vˈɛktɚɹ ʌv tˈiː', 'the generic type Vector<T>'),
    ('CPU', 'see-pee-YOU', 'sˌiːpˌiːjˈuː', 'letters'),
    ('HTTP', 'aitch-tee-tee-PEE', 'ˌeɪtʃtˌiːtˌiːpˈiː', 'letters'),
    ('JSON', 'JAY-son', 'dʒˈeɪsən', 'the common developer reading'),
    ('API', 'ay-pee-EYE', 'ˌeɪpˌiːˈaɪ', 'letters'),
]

import re
_ordered = sorted(LEXICON, key=lambda e: -len(e[0]))
PATTERN = re.compile('|'.join(r'(?<![\w.])' + re.escape(t) + r'(?![\w#])' for t, *_ in _ordered))
IPA = {t: ipa for t, _, ipa, _ in LEXICON}

def to_phonemes(text, phonemize):
    """phonemize everything except lexicon terms, which get their pinned phonemes. Returns (phonemes, terms used)."""
    out, used, pos = [], [], 0
    for m in PATTERN.finditer(text):
        chunk = text[pos:m.start()]
        if chunk.strip(): out.append(phonemize(chunk))
        out.append(IPA[m.group(0)]); used.append(m.group(0)); pos = m.end()
    tail = text[pos:]
    if tail.strip(): out.append(phonemize(tail))
    ph = ' '.join(p.strip() for p in out if p.strip())
    ph = re.sub(r'\s+([.,!?;:])', r'\1', ph)
    return ph, used

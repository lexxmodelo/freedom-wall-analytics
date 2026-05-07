/* Combined Taglish + English stopword list for word/keyword frequency. */
(function () {
  const EN = new Set([
    "the","a","an","and","or","but","if","then","else","of","in","on","at","to","for","with","by","from","as",
    "is","are","was","were","be","been","being","am","do","does","did","done","have","has","had","having",
    "i","me","my","mine","we","our","ours","you","your","yours","he","him","his","she","her","hers","it","its","they","them","their",
    "this","that","these","those","there","here","what","which","who","whom","whose","when","where","why","how",
    "not","no","nor","so","too","very","just","really","also","such","than","ever","never","always",
    "can","could","will","would","should","may","might","must","shall","ought","need","want",
    "about","above","after","again","against","all","any","because","before","below","between","both","each","few",
    "more","most","other","some","into","over","own","same","through","under","up","down","off","out",
    "yes","ok","okay","like","get","got","make","made","take","took","go","gone","going","come","came",
    "lol","lmao","omg","tbh","ngl","idk","idc","u","ur","tho","kinda","sorta",
    "hello","hey","hi","please","thank","thanks","thx","sorry","yeah","yup","nope",
    "guys","guyz","bro","sis","dude","fam","ate","kuya",
  ]);

  const TL = new Set([
    "ako","ikaw","ka","siya","kami","tayo","kayo","sila","ko","mo","niya","namin","natin","ninyo","nila",
    "akin","iyo","kanya","atin","amin","inyo","kanila",
    "ang","ng","mga","sa","kay","ni","na","at","pero","kaya","kasi","dahil","para","kung","kapag",
    "ay","may","mayroon","wala","walang","meron","oo","hindi","huwag","wag","din","rin",
    "ito","iyan","iyon","ganito","ganyan","ganoon","ganun","heto","hayan",
    "po","nga","naman","lang","lamang","muna","talaga","sana","baka","yata","pala",
    "yung","yun","yang","yon","ung","ang",
    "saan","kailan","paano","ano","sino","alin","bakit","ilan","gaano","kanino",
    "isa","dalawa","tatlo","apat","lima","anim","pito","walo","siyam","sampu",
    "araw","gabi","umaga","tanghali","hapon","lunes","martes","miyerkules","huwebes","biyernes","sabado","linggo",
    "tao","bagay","salita","oras","panahon","lugar",
    "gusto","ayaw","tingin","sabi","gawa","punta","balik","tulog","kain","inom",
    "akala","kase","etong","etoh",
    "uy","hoy","oh","ah","eh","huh","wow","grabe","sus","aba","hala","char","charot",
    "ba","mas","pinaka","sobra","masyado","bigla","biglang",
    "kahit","pati","kasama","kasunod","habang","bago","pagkatapos","tapos","saka",
    "haha","hehe","hihi","hoho","huhu","huhuhu","hahaha","hehehe",
    "ngayon","kanina","mamaya","kahapon","bukas","tuwing","palagi","minsan",
    "niyo","mag","nag","pag","mong","kong","sino",
    /* fillers / colloquial that were leaking into the keyword chart */
    "kita","nakita","makita","tingnan","nung","nun","nyo","nyong","iba","kayong","tayong",
    "lahat","tapos","tapo","kasi","kase","ganun","ganon","kelan","sino","sa","saan",
  ]);

  /* English contraction artifacts (apostrophes are stripped during tokenization,
     leaving "im", "dont", etc.). We keep these out of the trending-keywords chart. */
  const CONTRACTIONS = new Set([
    "im","ive","id","ill","youre","youve","youll","youd","theyre","theyve","theyll","theyd",
    "were","weve","well","wed","hes","shes","its","whos","whats","whens","wheres","whys","hows",
    "dont","doesnt","didnt","wont","wouldnt","couldnt","shouldnt","cant","cannot","mustnt",
    "isnt","arent","wasnt","werent","hasnt","havent","hadnt","aint",
    "lets","gonna","wanna","gotta",
  ]);

  /* System placeholders left over from the anonymisation pipeline. We strip the bracket
     form before lowercasing, but if any post had the lowercased fragment slip through
     we filter it explicitly here so an admin never sees "redacted" or "name" in a
     trending-keywords chart. */
  const SYSTEM = new Set([
    "redacted", "redacted_name", "name", "names",
    "professor", "professor_name", "department", "department_name",
    "campus", "campus_location", "school_name", "university_name",
    "fb", "messenger", "ig",
  ]);

  const STOPWORDS = new Set([...EN, ...TL, ...SYSTEM, ...CONTRACTIONS]);

  /* Tiny English singularizer so "students" and "student" merge in the keyword chart.
     Conservative rules — only collapse when the singular form is plausibly the same word
     (>=4 chars, common suffixes). Tagalog tokens generally don't take these suffixes,
     so the overlap is acceptable. */
  const IRREGULAR = {
    children: "child", men: "man", women: "woman", people: "person",
    feet: "foot", teeth: "tooth", mice: "mouse", geese: "goose",
  };
  function singularize(w) {
    if (!w || w.length < 4) return w;
    if (IRREGULAR[w]) return IRREGULAR[w];
    if (w.endsWith("ies") && w.length > 4) return w.slice(0, -3) + "y";
    if (w.endsWith("sses")) return w.slice(0, -2);
    if (w.endsWith("ches") || w.endsWith("shes") || w.endsWith("xes")) return w.slice(0, -2);
    if (w.endsWith("s") && !w.endsWith("ss") && !w.endsWith("us") && !w.endsWith("is")) {
      return w.slice(0, -1);
    }
    return w;
  }

  function tokenize(text) {
    if (!text) return [];
    /* CRITICAL: strip placeholders BEFORE lowercasing so the bracket regex matches.
       Previously this ran post-lowercase with an uppercase-only pattern, leaking
       "redacted" and "name" into frequency counts. */
    const stripped = String(text)
      .replace(/\[[A-Z_]+\]/gi, " ")
      .replace(/https?:\/\/\S+/g, " ");
    return stripped
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s']/gu, " ")
      .replace(/'/g, "")
      .split(/\s+/)
      /* Reject obvious junk first (length, digits, raw stopword like "tapos")
         BEFORE singularizing — otherwise the singularizer turns "tapos"
         into "tapo" and we miss the match. */
      .filter(w => w.length >= 3 && !STOPWORDS.has(w) && !/^\d+$/.test(w))
      .map(w => singularize(w))
      /* Re-check after singularizing so "students" → "student" is caught. */
      .filter(w => w.length >= 3 && !STOPWORDS.has(w));
  }

  function termFrequency(posts, max = 80) {
    const f = new Map();
    for (const p of posts) {
      for (const w of tokenize(p.text || "")) {
        f.set(w, (f.get(w) || 0) + 1);
      }
    }
    return [...f.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, max)
      .map(([word, count]) => ({ word, count }));
  }

  window.Stopwords = { STOPWORDS, tokenize, termFrequency, singularize };
})();

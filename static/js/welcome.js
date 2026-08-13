function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

const WELCOME_MESSAGES = {
  ja: {
    morning: [
      "おはようございます。今日は何から始めますか？",
      "朝のひと仕事、お手伝いします。",
      "すっきりした朝に、何を進めますか？",
      "朝イチのタスク、一緒に片づけましょう。",
      "コーヒー片手に、何を進めますか？",
    ],
    afternoon: [
      "午後の作業、何をお手伝いしましょうか？",
      "このあと進めたいことはありますか？",
      "今日の午後、どこから着手しますか？",
      "午後のひと息つきながら、何でもどうぞ。",
      "ひとつ余裕を持って、タスクを整理しませんか？",
    ],
    evening: [
      "夕方の作業も、お任せください。",
      "今日の仕上げ、お手伝いします。",
      "一日の締めくくりに、何かありますか？",
      "夕方のひととき、何を進めますか？",
    ],
    night: [
      "夜遅くまでお疲れさまです。何をお手伝いしましょうか？",
      "静かな夜も、じっくりお話しできます。",
      "夜更かしの作業、一緒に進めましょう。",
      "今日の最後のひと仕事、何ですか？",
    ],
    weekend: [
      "週末もお気軽に。何をお手伝いしましょうか？",
      "週末の時間を、もっと楽に使えるようお手伝いします。",
      "休日の作業やアイデア、一緒に整理しましょう。",
    ],
    fridayEvening: [
      "金曜の夕方、週末に向けて何か片づけますか？",
      "フライデーイブニング。軽く片づけたいことはありますか？",
    ],
    newYear: [
      "新年あけましておめでとうございます。今年もお気軽にどうぞ。",
      "新しい年のスタート、何からお手伝いしましょうか？",
    ],
    playful: [
      "アイデアをひねり出す相棒、ここにいます。",
      "今日の「ちょっと困った」、聞かせてください。",
      "思いついたことを、そのまま投げてみてください。",
    ],
  },
  en: {
    morning: [
      "Good morning. What would you like to start with?",
      "Ready for your morning tasks—how can I help?",
      "A fresh start—what should we tackle first?",
      "Morning mode on. What's on your list?",
      "Coffee optional—what can I help you with?",
    ],
    afternoon: [
      "Good afternoon. What can I help you with?",
      "What would you like to work on next?",
      "Afternoon check-in—where should we begin?",
      "Take a breath—what do you need done?",
      "Room to breathe—want to organize your tasks?",
    ],
    evening: [
      "Good evening. How can I help you wrap up?",
      "Let's finish strong—what's left today?",
      "Evening session—what should we tackle?",
      "Winding down—anything I can assist with?",
    ],
    night: [
      "Working late—how can I help?",
      "Quiet hours—happy to think through it with you.",
      "Night shift—what's the last thing on your plate?",
      "Still going—what do you need?",
    ],
    weekend: [
      "Weekend vibes—what can I help with?",
      "Hope you're enjoying the weekend. Need a hand?",
      "Saturday or Sunday—ideas and tasks welcome.",
    ],
    fridayEvening: [
      "Friday evening—anything to clear before the weekend?",
      "Almost weekend—light tasks or planning?",
    ],
    newYear: [
      "Happy New Year—glad you're here.",
      "New year, fresh start—what can I help with first?",
    ],
    playful: [
      "Your brainstorming buddy is here.",
      "Got a \"quick question\"? Throw it my way.",
      "No perfect prompt needed—just say what's on your mind.",
    ],
  },
  ko: {
    morning: [
      "좋은 아침입니다. 무엇부터 시작할까요?",
      "아침 업무, 도와드릴게요.",
      "상쾌한 아침, 무엇을 진행할까요?",
      "아침 첫 할 일, 함께 정리해 볼까요?",
      "커피 한 잔과 함께, 무엇을 도와드릴까요?",
    ],
    afternoon: [
      "오후 업무, 무엇을 도와드릴까요?",
      "이어서 진행하고 싶은 일이 있나요?",
      "오늘 오후, 어디서부터 시작할까요?",
      "오후 한숨 돌리며, 무엇이든 물어보세요.",
      "여유를 갖고 할 일을 정리해 볼까요?",
    ],
    evening: [
      "저녁 업무도 맡겨 주세요.",
      "오늘 마무리, 도와드릴게요.",
      "하루를 마무리하며 필요한 일이 있나요?",
      "저녁 시간, 무엇을 진행할까요?",
    ],
    night: [
      "늦게까지 수고하셨습니다. 무엇을 도와드릴까요?",
      "조용한 밤, 천천히 상의해 봐요.",
      "야근 작업, 함께 진행해요.",
      "오늘 마지막 할 일, 무엇인가요?",
    ],
    weekend: [
      "주말에도 편하게 물어보세요.",
      "주말 시간을 더 편하게 쓸 수 있도록 도와드릴게요.",
      "휴일 작업이나 아이디어, 함께 정리해요.",
    ],
    fridayEvening: [
      "금요일 저녁, 주말 전에 정리할 일이 있나요?",
      "불금이에요. 가볍게 마무리할 일이 있나요?",
    ],
    newYear: [
      "새해 복 많이 받으세요. 올해도 편하게 이용해 주세요.",
      "새해의 시작, 무엇부터 도와드릴까요?",
    ],
    playful: [
      "아이디어를 함께 뽑아낼 파트너가 여기 있어요.",
      "오늘의 \"잠깐 막힌 일\", 들려주세요.",
      "떠오른 생각을 그대로 던져 보세요.",
    ],
  },
};

function welcomeLocale(lang) {
  if (lang === "en") return "en";
  if (lang === "ko") return "ko";
  return "ja";
}

const SUGGESTION_POOLS = {
  ja: [
    { label: "丁寧なメールを書きたい", prompt: "ビジネスメールを丁寧に書くコツと例文を教えて" },
    { label: "文章を短くしてほしい", prompt: "長い文章を短くわかりやすく直すコツを教えて" },
    { label: "要約の仕方を教えて", prompt: "長い文章を3行で要約する手順を教えて" },
    { label: "アイデアを出してほしい", prompt: "新しい企画のアイデアを10個出して" },
    { label: "旅行の持ち物リストが欲しい", prompt: "3泊4日の国内旅行の持ち物チェックリストを作って" },
    { label: "週末の過ごし方を教えて", prompt: "雨の週末におすすめの過ごし方を5つ教えて" },
    { label: "夕食の献立を考えてほしい", prompt: "平日夜に30分で作れる夕食メニューを3つ提案して" },
    { label: "余り物で料理を作りたい", prompt: "カレーの余り物で作れる別メニューを教えて" },
    { label: "勉強の計画をしたい", prompt: "1週間で英単語100語覚える勉強プランを作って" },
    { label: "試験の復習法を教えて", prompt: "効率よく試験勉強するための復習スケジュールを作って" },
    { label: "タスクの優先順位を付けたい", prompt: "今日やるべきタスクの優先順位の付け方を教えて" },
    { label: "議事録のまとめ方を教えて", prompt: "会議の議事録をわかりやすくまとめるテンプレートを作って" },
    { label: "日本語を英語に翻訳して", prompt: "次の日本語を自然な英語に翻訳して：お世話になっております" },
    { label: "敬語を直してほしい", prompt: "次の文の敬語が正しいか直して：お忙しいところ恐れ入ります" },
    { label: "プレゼンの構成を考えてほしい", prompt: "5分プレゼンの構成案を3パターン作って" },
    { label: "断り文の例が欲しい", prompt: "お誘いをやんわり断るメッセージの例文を3つ作って" },
    { label: "お礼メールを書きたい", prompt: "面接後のお礼メールの例文を作って" },
    { label: "SNSの投稿文を作ってほしい", prompt: "カフェ紹介のInstagram投稿文を短く作って" },
    { label: "買い物リストを作ってほしい", prompt: "一人暮らしの1週間分の買い物リストを作って" },
    { label: "節約のコツを教えて", prompt: "食費を抑えるための具体的な節約術を10個教えて" },
    { label: "運動習慣をつけたい", prompt: "運動が続かない人向けに週3回の習慣プランを作って" },
    { label: "睡眠のリズムを整えたい", prompt: "寝つきを良くするための夜のルーティンを提案して" },
    { label: "子ども向けに説明してほしい", prompt: "小学生にもわかるように「税金」を説明して" },
    { label: "名前のアイデアが欲しい", prompt: "カフェの新メニュー名のアイデアを15個出して" },
    { label: "プレゼントを選びたい", prompt: "20代女性への誕生日プレゼント案を5つ教えて" },
    { label: "引っ越しの準備をしたい", prompt: "引っ越し1ヶ月前からのやることリストを作って" },
    { label: "家計を見直したい", prompt: "家計を見直すためのチェック項目を作って" },
    { label: "読書メモの作り方を教えて", prompt: "本を読んだあとに残す読書メモのテンプレートを作って" },
    { label: "旅行プランを作ってほしい", prompt: "京都日帰り旅行のモデルプランを作って" },
    { label: "今日の服装を相談したい", prompt: "気温15度・曇りの日の服装コーディネートを提案して" },
    { label: "雑談の話題を教えて", prompt: "初対面の人と盛り上がる雑談トピックを10個教えて" },
    { label: "目標の立て方を教えて", prompt: "3ヶ月で達成できる個人目標の立て方を教えて" },
    { label: "ストレスを軽くしたい", prompt: "仕事のストレスを軽くする方法を5つ教えて" },
    { label: "手紙の文例が欲しい", prompt: "祖父母への手紙の文例を作って" },
    { label: "習慣を続けたい", prompt: "毎日の習慣を続けるための記録シート案を作って" },
    { label: "料理のコツを教えて", prompt: "卵焼きをふわふわにするコツを教えて" },
    { label: "掃除の手順を教えて", prompt: "週末のお部屋掃除を効率よく進める手順を教えて" },
  ],
  en: [
    { label: "I want to write a polite email", prompt: "How do I write a polite professional email? Give tips and examples." },
    { label: "Can you shorten my writing?", prompt: "How can I make long writing shorter and clearer?" },
    { label: "How do I summarize this?", prompt: "Show me how to summarize a long article in three sentences." },
    { label: "Help me brainstorm ideas", prompt: "Give me 10 creative ideas for a weekend side project." },
    { label: "I need a packing list", prompt: "Create a packing checklist for a 4-day domestic trip." },
    { label: "What should I do this weekend?", prompt: "Suggest five fun things to do on a rainy weekend." },
    { label: "Suggest quick weeknight dinners", prompt: "Suggest three dinners I can cook in about 30 minutes." },
    { label: "What can I cook with leftovers?", prompt: "What can I cook with leftover curry ingredients?" },
    { label: "I want a study plan", prompt: "Build a one-week plan to learn 100 vocabulary words." },
    { label: "Help me plan exam review", prompt: "Create an efficient one-week exam review schedule." },
    { label: "How do I prioritize my tasks?", prompt: "How should I prioritize today's work tasks?" },
    { label: "Can you help with meeting notes?", prompt: "Give me a simple meeting-notes template." },
    { label: "Translate this to Japanese", prompt: "Translate this into natural Japanese: Thank you for your help." },
    { label: "Make my message sound nicer", prompt: "Make this message sound friendlier but still professional." },
    { label: "Help me outline a presentation", prompt: "Outline a 5-minute presentation in three structures." },
    { label: "How do I decline politely?", prompt: "Write three polite ways to decline an invitation." },
    { label: "I need a thank-you email", prompt: "Draft a short thank-you email after a job interview." },
    { label: "Write a short social post", prompt: "Write a short social post recommending a local cafe." },
    { label: "Make me a grocery list", prompt: "Create a one-week grocery list for one person." },
    { label: "How can I save on food?", prompt: "Give me 10 practical ways to lower food spending." },
    { label: "I want to start exercising", prompt: "Create a simple 3-days-per-week exercise plan for beginners." },
    { label: "Help me sleep better", prompt: "Suggest an evening routine to fall asleep more easily." },
    { label: "Explain this in simple terms", prompt: "Explain taxes in simple terms a teenager can understand." },
    { label: "Suggest some name ideas", prompt: "Suggest 15 names for a new cafe drink." },
    { label: "Help me pick a gift", prompt: "Suggest five birthday gift ideas for someone in their 20s." },
    { label: "I need a moving checklist", prompt: "Create a one-month moving preparation checklist." },
    { label: "Help me review my budget", prompt: "Give me a checklist to review my monthly budget." },
    { label: "How do I take reading notes?", prompt: "Create a template for book reading notes." },
    { label: "Plan a day trip for me", prompt: "Plan a one-day sightseeing trip with a morning-to-evening schedule." },
    { label: "What should I wear today?", prompt: "What should I wear on a cloudy 15°C day?" },
    { label: "Give me small-talk ideas", prompt: "Give me 10 easy small-talk topics for meeting someone new." },
    { label: "How do I set a 90-day goal?", prompt: "How do I set a realistic personal goal for the next 90 days?" },
    { label: "How can I reduce stress?", prompt: "Share five practical ways to reduce work stress." },
    { label: "Help me write a letter", prompt: "Draft a warm letter to grandparents." },
    { label: "I want to build daily habits", prompt: "Design a simple daily habit tracker I can reuse." },
    { label: "How do I cook fluffier eggs?", prompt: "How do I make fluffy scrambled eggs at home?" },
    { label: "What's a good cleaning routine?", prompt: "Give me an efficient weekend room-cleaning routine." },
  ],
  ko: [
    { label: "정중한 이메일을 쓰고 싶어요", prompt: "비즈니스 이메일을 정중하게 쓰는 요령과 예문을 알려줘" },
    { label: "글을 짧게 다듬어 주세요", prompt: "긴 글을 짧고 이해하기 쉽게 고치는 방법을 알려줘" },
    { label: "요약하는 법을 알려주세요", prompt: "긴 글을 3문장으로 요약하는 순서를 알려줘" },
    { label: "아이디어를 제안해 주세요", prompt: "새 기획 아이디어 10개를 제안해줘" },
    { label: "여행 짐 목록이 필요해요", prompt: "3박 4일 국내 여행 짐 체크리스트를 만들어줘" },
    { label: "주말에 뭐 하면 좋을까요?", prompt: "비 오는 주말에 추천할 만한 활동 5가지를 알려줘" },
    { label: "저녁 메뉴를 추천해 주세요", prompt: "평일 밤 30분 안에 만들 수 있는 저녁 메뉴 3가지를 제안해줘" },
    { label: "남은 재료로 요리하고 싶어요", prompt: "카레 남은 재료로 만들 수 있는 다른 요리를 알려줘" },
    { label: "공부 계획을 세우고 싶어요", prompt: "1주일에 영어 단어 100개 외우는 공부 계획을 만들어줘" },
    { label: "시험 복습법을 알려주세요", prompt: "효율적으로 시험 공부하는 복습 일정을 만들어줘" },
    { label: "업무 우선순위를 정하고 싶어요", prompt: "오늘 해야 할 일의 우선순위 정하는 방법을 알려줘" },
    { label: "회의록 정리를 도와주세요", prompt: "회의록을 이해하기 쉽게 정리하는 템플릿을 만들어줘" },
    { label: "한국어를 영어로 번역해 주세요", prompt: "다음 한국어를 자연스러운 영어로 번역해줘: 안녕하세요, 잘 부탁드립니다" },
    { label: "말투를 고쳐 주세요", prompt: "다음 문장이 정중한지 고쳐줘: 바쁘신 중에 죄송합니다" },
    { label: "발표 구성을 짜 주세요", prompt: "5분 발표 구성안을 3가지 패턴으로 만들어줘" },
    { label: "거절 메시지 예문이 필요해요", prompt: "부드럽게 초대를 거절하는 메시지 예문 3개를 만들어줘" },
    { label: "감사 메일을 쓰고 싶어요", prompt: "면접 후 감사 이메일 예문을 작성해줘" },
    { label: "SNS 게시글을 작성해 주세요", prompt: "카페 소개 인스타그램 게시글을 짧게 작성해줘" },
    { label: "장보기 목록을 만들어 주세요", prompt: "1인 가구 1주일 장보기 목록을 만들어줘" },
    { label: "식비 절약법을 알려주세요", prompt: "식비를 줄이는 구체적인 방법 10가지를 알려줘" },
    { label: "운동 습관을 만들고 싶어요", prompt: "운동이 잘 안 되는 사람을 위한 주 3회 운동 계획을 만들어줘" },
    { label: "잠을 더 잘 자고 싶어요", prompt: "잠들기 쉬운 저녁 루틴을 제안해줘" },
    { label: "쉽게 설명해 주세요", prompt: "초등학생도 이해할 수 있게 '세금'을 설명해줘" },
    { label: "이름 아이디어를 제안해 주세요", prompt: "카페 신메뉴 이름 아이디어 15개를 제안해줘" },
    { label: "선물을 골라 주세요", prompt: "20대 여성 생일 선물 아이디어 5가지를 알려줘" },
    { label: "이사 준비를 하고 싶어요", prompt: "이사 1개월 전부터 할 일 목록을 만들어줘" },
    { label: "가계를 점검하고 싶어요", prompt: "가계를 점검하는 체크 항목을 만들어줘" },
    { label: "독서 메모 만드는 법을 알려주세요", prompt: "책을 읽은 뒤 남길 독서 메모 템플릿을 만들어줘" },
    { label: "여행 일정을 짜 주세요", prompt: "경주 당일치기 여행 모델 일정을 만들어줘" },
    { label: "오늘 뭐 입을까요?", prompt: "기온 15도·흐린 날 옷차림을 제안해줘" },
    { label: "대화 주제를 알려주세요", prompt: "처음 만난 사람과 대화하기 좋은 주제 10가지를 알려줘" },
    { label: "목표 세우는 법을 알려주세요", prompt: "3개월 안에 달성할 개인 목표 세우는 방법을 알려줘" },
    { label: "스트레스를 줄이고 싶어요", prompt: "직장 스트레스를 줄이는 방법 5가지를 알려줘" },
    { label: "편지 예문이 필요해요", prompt: "조부모에게 보내는 편지 예문을 작성해줘" },
    { label: "습관을 꾸준히 하고 싶어요", prompt: "매일 습관을 기록하는 시트 안을 만들어줘" },
    { label: "요리 요령을 알려주세요", prompt: "계란말이를 부드럽게 만드는 요령을 알려줘" },
    { label: "청소 순서를 알려주세요", prompt: "주말 방 청소를 효율적으로 하는 순서를 알려줘" },
  ],
};

function pickFrom(pool) {
  return pool[Math.floor(Math.random() * pool.length)];
}

function shufflePick(pool, count) {
  const arr = pool.slice();
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr.slice(0, count);
}

function getTimeBucket(hour) {
  if (hour >= 5 && hour < 11) return "morning";
  if (hour >= 11 && hour < 17) return "afternoon";
  if (hour >= 17 && hour < 21) return "evening";
  return "night";
}

function isNewYearSeason(date) {
  const m = date.getMonth() + 1;
  const d = date.getDate();
  return (m === 12 && d === 31) || (m === 1 && d <= 3);
}

function isFridayEvening(date) {
  return date.getDay() === 5 && date.getHours() >= 17;
}

function isWeekend(date) {
  const day = date.getDay();
  return day === 0 || day === 6;
}

function pickWelcomeMessage(lang) {
  const locale = welcomeLocale(lang);
  const dict = WELCOME_MESSAGES[locale] || WELCOME_MESSAGES.ja;
  const now = new Date();
  const hour = now.getHours();
  const roll = Math.random();

  if (isNewYearSeason(now) && roll < 0.28) {
    return pickFrom(dict.newYear);
  }
  if (isFridayEvening(now) && roll < 0.22) {
    return pickFrom(dict.fridayEvening);
  }
  if (roll < 0.08) {
    return pickFrom(dict.playful);
  }
  if (isWeekend(now) && roll < 0.38) {
    return pickFrom(dict.weekend);
  }
  return pickFrom(dict[getTimeBucket(hour)]);
}

function updateWelcomeSuggestions() {
  const welcome = document.getElementById("welcome");
  if (!welcome || welcome.classList.contains("hidden")) return;
  const buttons = welcome.querySelectorAll(".suggestion");
  if (!buttons.length) return;
  const lang = window.__USER__?.language || "ja";
  const pool = SUGGESTION_POOLS[welcomeLocale(lang)] || SUGGESTION_POOLS.ja;
  const picks = shufflePick(pool, Math.min(buttons.length, 4));
  picks.forEach((item, i) => {
    const btn = buttons[i];
    btn.dataset.prompt = item.prompt;
    btn.innerHTML = '<i class="bi bi-arrow-90deg-right suggestion-icon"></i> ' + escapeHtml(item.label);
    btn.style.animationDelay = (0.06 * (i + 1)) + "s";
  });
  welcome.classList.add("suggestions-enter");
}

let welcomeUpdateQueued = false;
let welcomeUpdateRefresh = false;
let welcomeTypewriterTimer = null;
const TYPEWRITER_DELAY_MS = 55;

function applyWelcomeContent() {
  const h1 = document.getElementById("welcomeHeading");
  const welcome = document.getElementById("welcome");
  if (!h1 || !welcome || welcome.classList.contains("hidden")) return;
  const lang = window.__USER__?.language || "ja";
  const msg = pickWelcomeMessage(lang);
  typewrite(h1, msg, updateWelcomeSuggestions);
}

function typewrite(el, text, onDone) {
  if (welcomeTypewriterTimer) clearTimeout(welcomeTypewriterTimer);
  el.textContent = "";
  el.classList.add("welcome-typing");
  let i = 0;
  function tick() {
    if (i < text.length) {
      el.textContent = text.slice(0, i + 1);
      i++;
      welcomeTypewriterTimer = setTimeout(tick, TYPEWRITER_DELAY_MS);
    } else {
      welcomeTypewriterTimer = null;
      el.classList.remove("welcome-typing");
      if (onDone) onDone();
    }
  }
  tick();
}

function flushWelcomeUpdate() {
  const shouldRefresh = welcomeUpdateRefresh;
  welcomeUpdateQueued = false;
  welcomeUpdateRefresh = false;
  if (!shouldRefresh && window.__welcomeContentReady) return;
  applyWelcomeContent();
  window.__welcomeContentReady = true;
}

function updateWelcomeHeading(options = {}) {
  const refresh = Boolean(options.refresh ?? options.force);
  if (welcomeUpdateQueued) {
    welcomeUpdateRefresh = welcomeUpdateRefresh || refresh;
    return;
  }
  if (!refresh && window.__welcomeContentReady) return;
  welcomeUpdateRefresh = refresh;
  welcomeUpdateQueued = true;
  queueMicrotask(flushWelcomeUpdate);
}

function paintWelcomeIfVisible() {
  const welcome = document.getElementById("welcome");
  if (!welcome || welcome.classList.contains("hidden")) return;
  if (window.__welcomeContentReady) return;
  if (window.__SESSION_ID__) return;
  applyWelcomeContent();
  window.__welcomeContentReady = true;
}

window.pickWelcomeMessage = pickWelcomeMessage;
window.updateWelcomeHeading = updateWelcomeHeading;
paintWelcomeIfVisible();

const prevApplyLanguage = window.applyLanguage;
if (typeof prevApplyLanguage === "function") {
  window.applyLanguage = function (lang) {
    prevApplyLanguage(lang);
    updateWelcomeHeading({ refresh: true });
  };
}

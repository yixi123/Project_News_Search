// Since we're using CDNs, these are available directly on the window object
const { useState, useEffect, useMemo } = React;
const { motion, AnimatePresence } = window.Motion;

// --- UTILITIES ---

function getSpineClasses(importance) {
  if (importance <= 3) return "w-0.5 bg-slate-300";
  if (importance <= 7) return "w-1 bg-slate-400";
  if (importance <= 9) return "w-1.5 bg-blue-400 shadow-[0_0_8px_rgba(96,165,250,0.5)]";
  return "w-1.5 bg-gradient-to-b from-blue-500 to-purple-600 shadow-[0_0_15px_rgba(59,130,246,0.5)]";
}

function formatDateToMonthYearString(dateStr) {
  if (!dateStr) return "Unknown Date";
  // If it's a range like "Nov 17 - Nov 22, 2023", try to extract the year and month 
  // or just return the string if it's already a short text like "Nov 2023"
  const cleanStr = dateStr.split('-')[0].trim();
  const date = new Date(cleanStr);
  if (isNaN(date.getTime())) return dateStr;
  return date.toLocaleString('default', { month: 'long', year: 'numeric' });
}

function groupEventsByMonth(events) {
  const grouped = {};
  events.forEach(event => {
    const monthYear = formatDateToMonthYearString(event.date);
    if (!grouped[monthYear]) {
      grouped[monthYear] = [];
    }
    grouped[monthYear].push(event);
  });
  return Object.entries(grouped);
}

// Custom hook for local storage persistence
function useLocalStorage(key, initialValue) {
  const [storedValue, setStoredValue] = useState(() => {
    try {
      const item = window.localStorage.getItem(key);
      return item ? JSON.parse(item) : initialValue;
    } catch (error) {
      console.warn(error);
      return initialValue;
    }
  });

  const setValue = value => {
    try {
      setStoredValue(prevState => {
        const valueToStore = value instanceof Function ? value(prevState) : value;
        window.localStorage.setItem(key, JSON.stringify(valueToStore));
        return valueToStore;
      });
    } catch (error) {
      console.warn(error);
    }
  };

  return [storedValue, setValue];
}

// Replace this with your current ngrok or tunnel URL.
const API_BASE_URL = "";

// --- ICONS (Heroicons) ---
const SearchIcon = () => (
  <svg className="w-5 h-5 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
  </svg>
);

const ChevronIcon = ({ open }) => (
  <svg className={`w-5 h-5 transition-transform duration-300 ${open ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
  </svg>
);

// --- COMPONENTS ---

const ROTATING_PLACEHOLDERS = [
  "OpenAI",
  "SpaceX launches",
  "AI regulations in 2023",
  "Global chip shortage",
  "Covid-19 pandemic",
  "Brexit negotiations",
  "Paris Climate Agreement",
  "US Presidential Election 2020",
  "Elon Musk Twitter acquisition",
  "UK Prime Minister changes",
  "Suez Canal blockage",
  "Boeing 737 MAX grounding",
  "Silicon Valley Bank collapse"
];

const SearchPanel = ({ query, setQuery, onSearch, isLoading, isTracing, isDarkMode }) => {
  const [placeholderIndex, setPlaceholderIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setPlaceholderIndex((prev) => (prev + 1) % ROTATING_PLACEHOLDERS.length);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim()) {
      onSearch(query);
    }
  };

  return (
    <div className={`sticky top-0 z-50 py-6 px-4 backdrop-blur-md border-b shadow-sm ${isDarkMode ? 'bg-slate-950/85 border-slate-800 shadow-black/20' : 'bg-slate-50/80 border-slate-200'}`}>
      <div className="max-w-4xl mx-auto flex items-center gap-6">
        <h1 className={`text-2xl font-bold tracking-tight hidden sm:block ${isDarkMode ? 'text-slate-100' : 'text-slate-900'}`}>NewsTrace</h1>
        <form onSubmit={handleSubmit} className="flex-1 w-full">
          <div className="relative flex items-center">
            <div className="absolute left-4">
              <SearchIcon />
            </div>
            <input 
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={isLoading}
              placeholder={ROTATING_PLACEHOLDERS[placeholderIndex]}
              className={`w-full pl-12 pr-4 py-3 rounded-full shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-all disabled:opacity-50 ${isDarkMode ? 'bg-slate-900 border-slate-700 text-slate-100 placeholder:text-slate-400 disabled:bg-slate-800' : 'bg-white border-slate-200 disabled:bg-slate-100'}`}
            />
            <button 
              type="submit" 
              disabled={isLoading || isTracing || !query.trim()}
              className={`absolute right-2 px-6 py-1.5 rounded-full text-sm font-medium disabled:opacity-50 transition-colors ${isDarkMode ? 'bg-slate-100 text-slate-900 hover:bg-white' : 'bg-slate-900 text-white hover:bg-slate-800'}`}
            >
              {isLoading || isTracing ? "Tracing..." : "Trace"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

const NewsCard = ({ event, isDarkMode }) => {
  const [expanded, setExpanded] = useState(false);
  const [showAllSources, setShowAllSources] = useState(false);
  
  const hasSubEvents = event.sub_events && event.sub_events.length > 0;
  // Map old schema and new JSON schema together
  const isMajor = event.type === 'major_event' || typeof event.milestone_title !== 'undefined';
  const headline = event.milestone_title || event.headline;
  const dateStr = event.date_range || event.date;
  const summary = event.synthesis || event.summary;
  
  // Extract sources from sub_events if top-level sources don't exist in new schema
  const sources = event.sources || (hasSubEvents ? event.sub_events.map(sub => sub.url).filter(url => url) : []);

  return (
    <div className={`relative rounded-2xl shadow-sm border hover:shadow-md transition-all group ${isDarkMode ? 'bg-slate-900 border-slate-700 text-slate-100 hover:border-slate-600' : 'bg-white border-slate-200 text-slate-900'} ${isMajor ? (isDarkMode ? 'p-6 border-sky-900 ring-1 ring-sky-950' : 'p-6 border-blue-100 ring-1 ring-blue-50') : 'p-4'}`}>
      <div className={`flex justify-between items-start ${isMajor ? 'mb-3' : 'mb-2'}`}>
        <div>
          {isMajor && (
            <span className={`inline-block px-2.5 py-1 text-xs font-semibold rounded-md mb-2 tracking-wide uppercase shadow-sm ${isDarkMode ? 'bg-rose-950 text-rose-200' : 'bg-red-100 text-red-700'}`}>
              Major Event
            </span>
          )}
          <div className={`text-sm font-medium mb-1 ${isDarkMode ? 'text-slate-400' : 'text-slate-500'}`}>{dateStr}</div>
        </div>
      </div>
      
      <h3 className={`font-semibold ${isDarkMode ? 'text-slate-50' : 'text-slate-900'} ${isMajor ? 'text-xl mb-2' : 'text-lg mb-1.5'}`}>{headline}</h3>
      <p 
        className={`leading-relaxed ${isDarkMode ? 'text-slate-300' : 'text-slate-600'} ${isMajor ? 'mb-4 text-base' : 'mb-3 text-sm line-clamp-2'}`}
        title={!isMajor ? summary : undefined}
      >
        {summary}
      </p>

      {/* Sources list */}
      {sources && sources.length > 0 && (
        <div className={`flex flex-wrap gap-2 ${hasSubEvents ? 'mb-4' : 'mb-1'}`}>
          <span className={`text-xs my-auto uppercase tracking-wide font-medium ${isDarkMode ? 'text-slate-400' : 'text-slate-400'}`}>Sources:</span>
          {(showAllSources ? sources : sources.slice(0, 3)).map((url, i) => {
            try { 
              const domain = new URL(url).hostname.replace('www.', '');
              return (
                <a key={i} href={url} target="_blank" rel="noopener noreferrer" className={`text-xs px-2 py-1 transition-colors rounded-md ${isDarkMode ? 'bg-slate-800 text-sky-300 hover:text-slate-50 hover:bg-sky-500' : 'bg-slate-100 text-blue-600 hover:text-white hover:bg-blue-500'}`}>
                  {domain}
                </a>
              );
            } catch { return null; }
          })}
          {!showAllSources && sources.length > 3 && (
            <button 
              onClick={() => setShowAllSources(true)} 
              className={`text-xs px-2 py-1 transition-colors rounded-md ${isDarkMode ? 'bg-slate-800 text-slate-300 hover:bg-slate-700' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
            >
              +{sources.length - 3} more
            </button>
          )}
          {showAllSources && sources.length > 3 && (
            <button 
              onClick={() => setShowAllSources(false)} 
              className={`text-xs px-2 py-1 transition-colors rounded-md ${isDarkMode ? 'bg-slate-800 text-slate-300 hover:bg-slate-700' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
            >
              Show less
            </button>
          )}
        </div>
      )}

      {hasSubEvents && (
        <div className={`mt-4 pt-4 border-t ${isDarkMode ? 'border-slate-700' : 'border-slate-100'}`}>
          <button 
            onClick={() => setExpanded(!expanded)}
            className={`flex items-center justify-between w-full text-sm font-medium transition-colors ${isDarkMode ? 'text-slate-200 hover:text-sky-300' : 'text-slate-700 hover:text-blue-600'}`}
          >
            <span>{event.sub_events.length} Connected Sub-events</span>
            <ChevronIcon open={expanded} />
          </button>
          
          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.3, ease: "easeInOut" }}
                className="overflow-hidden"
              >
                <div className={`pt-4 pl-4 border-l-2 border-dashed ml-2 mt-2 space-y-4 ${isDarkMode ? 'border-slate-600' : 'border-slate-300'}`}>
                  {event.sub_events.map((sub, i) => (
                    <div key={i} className="relative">
                      {/* Dashed connector line horizontal stub */}
                      <div className={`absolute -left-4 top-2.5 w-3 border-t-2 border-dashed ${isDarkMode ? 'border-slate-600' : 'border-slate-300'}`}></div>
                      {sub.date && <div className={`text-xs mb-0.5 ${isDarkMode ? 'text-slate-400' : 'text-slate-500'}`}>{sub.date}</div>}
                      <h4 className={`text-sm font-semibold ${isDarkMode ? 'text-slate-100' : 'text-slate-800'}`}>{sub.headline}</h4>
                      <p className={`text-sm mt-1 ${isDarkMode ? 'text-slate-300' : 'text-slate-600'}`}>{sub.summary}</p>
                      {sub.url && (
                        <a href={sub.url} target="_blank" rel="noopener noreferrer" className={`inline-block mt-2 text-xs font-semibold transition-colors ${isDarkMode ? 'text-sky-300 hover:text-sky-200' : 'text-blue-600 hover:text-blue-800'}`}>
                          Read Source ↗
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
};

const TimelineSummary = ({ timeline, isDarkMode }) => {
  const majorEvents = timeline.filter(event => event.type === "major_event");

  if (majorEvents.length === 0) return null;

  return (
    <div className="max-w-5xl mx-auto mt-6 px-4">
      <div className={`backdrop-blur-xl border shadow-sm rounded-xl p-5 ${isDarkMode ? 'bg-slate-900/80 border-slate-800' : 'bg-white/70 border-slate-200'}`}>
        <h3 className={`text-sm font-bold uppercase tracking-widest mb-4 flex items-center gap-2 ${isDarkMode ? 'text-slate-100' : 'text-slate-800'}`}>
          <span>Major Events Summary</span>
          <span className={`${isDarkMode ? 'bg-slate-100 text-slate-900' : 'bg-slate-900 text-white'} text-[10px] px-2 py-0.5 rounded-full`}>{majorEvents.length}</span>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {majorEvents.map((event) => (
            <a 
              key={event.id}
              href={`#${event.id}`}
              className={`group block p-3 rounded-lg border transition-all text-left ${isDarkMode ? 'bg-slate-800 hover:bg-slate-700 border-slate-700 hover:border-slate-600' : 'bg-slate-50 hover:bg-blue-50 border-slate-100 hover:border-blue-200'}`}
            >
              <div className={`text-xs font-semibold mb-1 ${isDarkMode ? 'text-sky-300' : 'text-blue-600'}`}>{event.date}</div>
              <div className={`text-sm font-medium group-hover:line-clamp-2 leading-snug ${isDarkMode ? 'text-slate-100 group-hover:text-white' : 'text-slate-800 group-hover:text-blue-900'}`}>
                {event.headline}
              </div>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
};

const TimelineFeed = ({ timeline, isDarkMode }) => {
  const groupedTimeline = useMemo(() => groupEventsByMonth(timeline), [timeline]);

  return (
    <div className="max-w-5xl mx-auto py-8 px-4">
      {groupedTimeline.map(([monthYear, events]) => (
        <div key={monthYear} className="relative mb-8">
          {/* Sticky Month Header */}
          <div className="sticky top-[104px] z-40 flex justify-center mb-4 pointer-events-none">
            <div className={`backdrop-blur px-3 py-1 text-sm rounded-full font-medium shadow-md pointer-events-auto ${isDarkMode ? 'bg-slate-100/95 text-slate-900 shadow-black/10' : 'bg-slate-900/90 text-white shadow-slate-900/10'}`}>
              {monthYear}
            </div>
          </div>

          <div className="relative">
            {/* The Central Spine */}
            <div className="absolute left-4 md:left-1/2 transform md:-translate-x-1/2 top-0 bottom-0 flex justify-center w-6 md:w-8">
              <div className={`h-full w-0.5 ${isDarkMode ? 'bg-slate-700' : 'bg-slate-200'}`}></div>
            </div>

            {/* Render Events Alternating */}
            <div className="space-y-8 md:space-y-6">
              {events.map((event, index) => {
                const isLeft = index % 2 === 0;
                return (
                  <div id={event.id} key={`${event.date}-${index}`} className="relative flex items-center md:justify-center scroll-mt-[180px]">
                    
                    {/* Dynamic Spine Node matching Event Importance */}
                    <div className="absolute left-4 md:left-1/2 transform md:-translate-x-1/2 flex justify-center z-10 w-6 md:w-8 pointer-events-none">
                       <div className={`h-16 ${getSpineClasses(event.importance)} rounded-full`}></div>
                    </div>

                    {/* Content Box */}
                    <div className={`w-full flex ${isLeft ? 'md:justify-start md:pr-12' : 'md:justify-end md:pl-12'} items-center pl-14 pr-2 md:px-0`}>
                      <div className={`w-full md:w-5/12 ${isLeft ? 'md:mr-auto' : 'md:ml-auto'}`}>
                        <NewsCard event={event} isDarkMode={isDarkMode} />
                      </div>
                    </div>

                    {/* Connector line (desktop only) */}
                    <div className={`hidden md:block absolute top-1/2 transform -translate-y-1/2 ${isLeft ? 'right-1/2 mr-8' : 'left-1/2 ml-8'} w-8 border-t-2 border-dashed z-0 ${isDarkMode ? 'border-slate-600' : 'border-slate-300'}`}></div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

const FeedbackPanel = ({ onSubmit, isSubmitting, status, onClose, isDarkMode }) => {
  const [message, setMessage] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit(message, () => setMessage(""));
  };

  return (
    <div
      id="feedback"
      className={`fixed inset-0 z-50 flex items-center justify-center px-4 py-8 ${isDarkMode ? 'bg-slate-950/70' : 'bg-slate-950/45'}`}
      onClick={onClose}
    >
      <div
        className={`relative w-full max-w-2xl backdrop-blur-sm border rounded-3xl shadow-2xl p-6 md:p-8 ${isDarkMode ? 'bg-slate-900/95 border-slate-700 text-slate-100' : 'bg-white/95 border-slate-200 text-slate-900'}`}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className={`absolute right-4 top-4 inline-flex h-9 w-9 items-center justify-center rounded-full border transition-colors ${isDarkMode ? 'border-slate-700 text-slate-300 hover:text-slate-50 hover:bg-slate-800' : 'border-slate-200 text-slate-500 hover:text-slate-900 hover:bg-slate-100'}`}
          aria-label="Close feedback form"
        >
          ×
        </button>

        <div className="flex items-start justify-between gap-4 flex-col md:flex-row md:items-center mb-4 pr-10">
          <div>
            <h3 className={`text-xl font-bold ${isDarkMode ? 'text-slate-50' : 'text-slate-900'}`}>Share feedback</h3>
            <p className={`text-sm mt-1 ${isDarkMode ? 'text-slate-300' : 'text-slate-600'}`}>Tell us what worked, what broke, or what you want improved.</p>
          </div>
          {status && (
            <div className={`text-sm font-medium px-3 py-2 rounded-full ${isDarkMode ? 'bg-slate-800 text-slate-200' : 'bg-slate-100 text-slate-700'}`}>
              {status}
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={4}
            placeholder="Write your feedback here..."
            className={`w-full rounded-2xl border px-4 py-3 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 resize-y ${isDarkMode ? 'border-slate-700 bg-slate-950 text-slate-100 placeholder:text-slate-500' : 'border-slate-200 bg-white text-slate-800'}`}
          />
          <div className="flex items-end justify-end gap-3 flex-col sm:flex-row">
            <button
              type="submit"
              disabled={isSubmitting || !message.trim()}
              className={`inline-flex items-center justify-center px-5 py-2.5 rounded-full text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${isDarkMode ? 'bg-slate-100 text-slate-900 hover:bg-white' : 'bg-slate-900 text-white hover:bg-slate-800'}`}
            >
              {isSubmitting ? "Sending..." : "Send feedback"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

const Footer = ({ onOpenFeedback, onNavigateHome, homeLabel, isDarkMode, onToggleDarkMode, isHomeDisabled, onToggleRetrieval, showRetrieval, retrieverOnline }) => (
  <footer className={`fixed bottom-0 left-0 w-full border-t backdrop-blur-sm z-50 ${isDarkMode ? 'border-slate-800 bg-slate-950/80' : 'border-slate-200 bg-white/70'}`}>
    <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between gap-4 text-sm text-slate-600">
      <div className="flex items-center gap-3">
        <span className={`font-medium ${isDarkMode ? 'text-slate-200' : 'text-slate-700'}`}>NewsTrace</span>
        <div className="text-xs flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${typeof retrieverOnline !== 'undefined' && retrieverOnline === true ? 'bg-emerald-400' : typeof retrieverOnline !== 'undefined' && retrieverOnline === null ? 'bg-slate-400' : 'bg-rose-400'}`}></span>
          <span className={`${isDarkMode ? 'text-slate-300' : 'text-slate-700'}`}>{retrieverOnline ? 'Retriever online' : retrieverOnline === null ? 'Checking retriever...' : 'Retriever offline'}</span>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <button type="button" onClick={onToggleDarkMode} className={`transition-colors ${isDarkMode ? 'text-slate-300 hover:text-white' : 'hover:text-slate-900'}`}>
          {isDarkMode ? 'Light Mode' : 'Dark Mode'}
        </button>
        <button type="button" onClick={onOpenFeedback} className={`transition-colors ${isDarkMode ? 'text-slate-300 hover:text-white' : 'hover:text-slate-900'}`}>Feedback</button>
        <button type="button" onClick={onToggleRetrieval} className={`transition-colors ${isDarkMode ? 'text-slate-300 hover:text-white' : 'hover:text-slate-900'} ${showRetrieval ? 'font-semibold' : ''}`}>{showRetrieval ? 'Hide Sources' : 'View Sources'}</button>
        <button
          type="button"
          onClick={onNavigateHome}
          disabled={isHomeDisabled}
          className={`transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${isDarkMode ? 'text-slate-300 hover:text-white' : 'hover:text-slate-900'}`}
        >
          {homeLabel}
        </button>
      </div>
    </div>
  </footer>
);

const App = () => {
  const [timeline, setTimeline] = useLocalStorage('newsTrace_timeline', null);
  const [query, setQuery] = useLocalStorage('newsTrace_query', '');
  const [isTracing, setIsTracing] = useLocalStorage('newsTrace_isTracing', false);
  const [progressMsg, setProgressMsg] = useState("Initializing trace...");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [feedbackStatus, setFeedbackStatus] = useState("");
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
  const [isFeedbackOpen, setIsFeedbackOpen] = useState(false);
  const [viewTimeline, setViewTimeline] = useLocalStorage('newsTrace_viewTimeline', false);
  const [isDarkMode, setIsDarkMode] = useLocalStorage('newsTrace_isDarkMode', false);
  const [retrievalArticles, setRetrievalArticles] = useState(null);
  const [showRetrieval, setShowRetrieval] = useLocalStorage('newsTrace_showRetrieval', false);
  const [retrieverOnline, setRetrieverOnline] = useState(null);
  const [isBouncerRejected, setIsBouncerRejected] = useState(false);
  const [isSensitive, setIsSensitive] = useState(false);
  const [sortSourcesBy, setSortSourcesBy] = useState('similarity'); // 'similarity', 'newest', or 'oldest'

  const checkRetriever = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/health`, {
        method: 'GET',
        headers: {
          'ngrok-skip-browser-warning': 'true',
          'Bypass-Tunnel-Reminder': 'true',
          'Accept': 'application/json'
        }
      });
      setRetrieverOnline(res.ok);
    } catch (err) {
      setRetrieverOnline(false);
    }
  };

  useEffect(() => {
    checkRetriever();
  }, []);

  useEffect(() => {
    if (isTracing && query) {
      handleSearch(query, true);
    }
  }, []); // Run once on mount

  const handleSearch = (searchQuery, isResume = false) => {
    setIsLoading(true);
    setError(null);
    setViewTimeline(true);
    
    // If not resuming, we reset the timeline and update query
    if (!isResume) {
      setTimeline(null); 
      setQuery(searchQuery);
      // Clear previous retrieval trace when starting a fresh search
      setRetrievalArticles(null);
      setShowRetrieval(false);
      setIsBouncerRejected(false);
      setIsSensitive(false);
    }
    setIsTracing(true);
    setProgressMsg(isResume ? "Resuming trace..." : "Connecting to server...");

    // We need to deduplicate events if we are resuming, because the server replays all events.
    // An easy way is to clear the timeline right as we receive the first actual event from the server.
    let hasClearedForReplay = !isResume; 

    // Built-in EventSource doesn't support custom headers (like ngrok-skip-browser-warning).
    // So we use standard fetch() and manually parse the streamed Server-Sent Events.
    const abortController = new AbortController();

    fetch(`${API_BASE_URL}/api/news?query=${encodeURIComponent(searchQuery)}`, {
      method: "GET",
      headers: {
        "ngrok-skip-browser-warning": "true",
        "Bypass-Tunnel-Reminder": "true",
        "Accept": "text/event-stream"
      },
      signal: abortController.signal
    })
    .then(async (response) => {
      if (!response.ok) throw new Error("Network response was not ok");
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          setIsLoading(false);
          setIsTracing(false);
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        // Keep the last incomplete line in the buffer
        buffer = lines.pop();

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i];

          if (line.startsWith("event: close")) {
            abortController.abort();
            setIsLoading(false);
            setIsTracing(false);
          } else if (line.startsWith("data: ")) {
            const dataStr = line.substring(6).trim();
            if (!dataStr || dataStr === "{}") continue;

            try {
              const data = JSON.parse(dataStr);
              if (data.type === "progress") {
                setProgressMsg(data.message);
              } else if (data.type === "bouncer_invalid") {
                setIsBouncerRejected(true);
                setProgressMsg(data.message || "Your query was rejected.");
              } else if (data.type === "retrieval") {
                // Keep the pure data, but use a memo or derive it in render. We set the raw articles from server.
                const articles = Array.isArray(data.articles) ? data.articles : [];
                setRetrievalArticles(articles);
                // open sidebar automatically when retrieval arrives
                setShowRetrieval(true);
              } else if (data.type === "sensitive") {
                setIsSensitive(true);
                setProgressMsg(data.message || "Sensitive content detected.");
              } else {
                const transformedData = {
                  ...data,
                  id: `event-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
                  date: data.date_range || data.date,
                  headline: data.milestone_title || data.headline,
                  summary: data.synthesis || data.summary,
                  type: 'major_event',
                  importance: 10,
                  sources: data.sources || (data.sub_events ? data.sub_events.map(s => s.url).filter(Boolean) : [])
                };
                setTimeline(prev => {
                  if (!hasClearedForReplay) {
                    hasClearedForReplay = true;
                    return [transformedData];
                  }
                  return [...(Array.isArray(prev) ? prev : []), transformedData];
                });
              }
            } catch (err) {
              console.error("Error parsing streaming data", err);
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name === "AbortError") return; // we aborted the fetch intentionally
      console.error(err);
      setIsLoading(false);
      setIsTracing(false);
      setTimeline(prev => {
        if (!prev || prev.length === 0) setError("Failed to fetch data or connection closed.");
        return prev;
      });
    });
  };

  const handleFeedbackSubmit = async (message, onSuccess) => {
    try {
      setIsSubmittingFeedback(true);
      setFeedbackStatus("Sending feedback...");

      const response = await fetch(`${API_BASE_URL}/api/feedback`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'ngrok-skip-browser-warning': 'true',
          'Bypass-Tunnel-Reminder': 'true'
        },
        body: JSON.stringify({
          message,
          query,
          page: window.location.pathname,
        }),
      });

      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.error || 'Failed to submit feedback.');
      }

      setFeedbackStatus('Thanks for the feedback.');
      onSuccess();
      setTimeout(() => setIsFeedbackOpen(false), 700);
    } catch (err) {
      setFeedbackStatus(err.message || 'Failed to submit feedback.');
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  const hasTimelineCache = Array.isArray(timeline) && timeline.length > 0;

  const handleNavigateHome = () => {
    setError(null);
    setIsLoading(false);
    setIsTracing(false);
    setIsBouncerRejected(false);
    setIsSensitive(false);
    setProgressMsg("Initializing trace...");
    setFeedbackStatus("");
    setIsFeedbackOpen(false);

    if (hasTimelineCache) {
      setViewTimeline(prev => !prev);
    } else {
      setViewTimeline(false);
    }
  };

  // If there's no data initialized but we just landed, we won't show anything 
  // until the user presses trace.

  const sortedRetrievalArticles = useMemo(() => {
    if (!retrievalArticles) return null;
    return [...retrievalArticles].sort((a, b) => {
      if (sortSourcesBy === 'newest') {
        const dateA = new Date(a.date).getTime();
        const dateB = new Date(b.date).getTime();
        return (isNaN(dateB) ? 0 : dateB) - (isNaN(dateA) ? 0 : dateA);
      } else if (sortSourcesBy === 'oldest') {
        const dateA = new Date(a.date).getTime();
        const dateB = new Date(b.date).getTime();
        return (isNaN(dateA) ? 0 : dateA) - (isNaN(dateB) ? 0 : dateB);
      }
      return (b.score || 0) - (a.score || 0); // similarity default
    });
  }, [retrievalArticles, sortSourcesBy]);

  return (
    <div className={`min-h-screen flex flex-col relative transition-colors duration-300 pb-28 ${isDarkMode ? 'bg-slate-950 text-slate-100' : 'bg-slate-50 text-slate-900'}`}>
      <SearchPanel query={query} setQuery={setQuery} onSearch={handleSearch} isLoading={isLoading} isTracing={isTracing} isDarkMode={isDarkMode} />
      
      {error && (
        <div className={`max-w-4xl mx-auto mt-8 p-4 rounded-xl shadow-sm text-center ${isDarkMode ? 'bg-rose-950/60 border border-rose-900 text-rose-200' : 'bg-red-50 border border-red-200 text-red-700'}`}>
          <p className="font-semibold">Error Loading Trace</p>
          <p className="text-sm opacity-80">{error}</p>
        </div>
      )}
      
      {isSensitive && (
        <div className={`max-w-4xl mx-auto mt-8 p-4 rounded-xl shadow-sm text-center ${isDarkMode ? 'bg-violet-950/60 border border-violet-900 text-violet-200' : 'bg-purple-50 border border-purple-200 text-purple-800'}`}>
          <p className="font-semibold">⚠️ Timeline Cannot Be Generated</p>
          <p className="text-sm opacity-90">This query contains sensitive or geopolitical information that our LLM cannot process. Please try a different search topic.</p>
        </div>
      )}
      
      {!isLoading && (!timeline || timeline.length === 0) && progressMsg && progressMsg !== "Initializing trace..." && progressMsg !== "Connecting to server..." && progressMsg !== "Generating chronological timeline..." && !error && !isSensitive && viewTimeline && (
        <div className={`max-w-4xl mx-auto mt-8 p-4 rounded-xl shadow-sm text-center ${isDarkMode ? 'bg-amber-950/60 border border-amber-900 text-amber-200' : 'bg-orange-50 border border-orange-200 text-orange-800'}`}>
          <p className="font-semibold">Notice</p>
          <p className="text-sm opacity-90">{progressMsg}</p>
        </div>
      )}

      {/* First-Time User Introduction */}
      {!isLoading && !viewTimeline && (!progressMsg || progressMsg === "Initializing trace...") && !error && (
        <div id="intro" className="max-w-4xl mx-auto mt-16 px-4 md:px-0 opacity-0 animate-[fadeIn_0.5s_ease-out_forwards] scroll-mt-24">
          <div className={`backdrop-blur-sm rounded-3xl shadow-lg border p-8 md:p-12 text-center ${isDarkMode ? 'bg-slate-900/85 border-slate-800 text-slate-100' : 'bg-white/80 border-slate-200 text-slate-800'}`}>
            <div className="w-16 h-16 mx-auto mb-6 bg-gradient-to-tr from-blue-500 to-indigo-500 rounded-2xl flex items-center justify-center shadow-md text-white">
              <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9.5a2.5 2.5 0 00-2.5-2.5H15M9 11l3 3L22 4" />
              </svg>
            </div>
            <h2 className={`text-3xl md:text-4xl font-extrabold tracking-tight mb-4 ${isDarkMode ? 'text-slate-50' : 'text-slate-900'}`}>
              Welcome to NewsTrace
            </h2>
            <p className={`text-lg md:text-xl mb-10 max-w-2xl mx-auto leading-relaxed ${isDarkMode ? 'text-slate-300' : 'text-slate-600'}`}>
              Discover the full story behind the headlines. Enter a topic, company, or global event to instantly generate a comprehensive, AI-powered chronological timeline compiled from verified news sources.
            </p>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-left mb-8">
              <div className={`p-6 rounded-2xl border transition hover:shadow-md hover:-translate-y-1 duration-300 ${isDarkMode ? 'bg-slate-950/70 border-slate-800' : 'bg-slate-50 border-slate-100'}`}>
                <div className="text-xl mb-3">🔍</div>
                <h3 className={`font-bold mb-2 ${isDarkMode ? 'text-slate-50' : 'text-slate-900'}`}>1. Ask Anything</h3>
                <p className={`text-sm leading-relaxed ${isDarkMode ? 'text-slate-300' : 'text-slate-600'}`}>Search for complex global events, historical milestones, or specific companies (e.g., "The rise of AI model tech").</p>
              </div>
              <div className={`p-6 rounded-2xl border transition hover:shadow-md hover:-translate-y-1 duration-300 ${isDarkMode ? 'bg-slate-950/70 border-slate-800' : 'bg-slate-50 border-slate-100'}`}>
                <div className="text-xl mb-3">🧠</div>
                <h3 className={`font-bold mb-2 ${isDarkMode ? 'text-slate-50' : 'text-slate-900'}`}>2. AI Analysis</h3>
                <p className={`text-sm leading-relaxed ${isDarkMode ? 'text-slate-300' : 'text-slate-600'}`}>Our backend semantic search isolates thousands of articles while the LLM categorizes and verifies key events.</p>
              </div>
              <div className={`p-6 rounded-2xl border transition hover:shadow-md hover:-translate-y-1 duration-300 ${isDarkMode ? 'bg-slate-950/70 border-slate-800' : 'bg-slate-50 border-slate-100'}`}>
                <div className="text-xl mb-3">⚡</div>
                <h3 className={`font-bold mb-2 ${isDarkMode ? 'text-slate-50' : 'text-slate-900'}`}>3. Track the Trace</h3>
                <p className={`text-sm leading-relaxed ${isDarkMode ? 'text-slate-300' : 'text-slate-600'}`}>Watch your custom timeline stream onto the page in real-time, complete with impact tracking and native citations.</p>
              </div>
            </div>
            
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
              <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-xs font-medium border ${isDarkMode ? 'bg-sky-950/60 text-sky-200 border-sky-900' : 'bg-blue-50 text-blue-700 border-blue-100'}`}>
                <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Note: The indexed dataset spans securely from January 2016 to May 2026.
              </div>
              <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-xs font-medium border ${isDarkMode ? 'bg-amber-950/60 text-amber-200 border-amber-900' : 'bg-amber-50 text-amber-700 border-amber-100'}`}>
                <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Generation takes approx. 1 minute.
              </div>
            </div>

            {/* Try This section */}
            <div className={`mt-10 pt-8 border-t flex flex-col items-center justify-center gap-4 ${isDarkMode ? 'border-slate-800' : 'border-slate-100'}`}>
              <span className={`text-sm font-semibold uppercase tracking-wider ${isDarkMode ? 'text-slate-400' : 'text-slate-500'}`}>Try tracing events</span>
              <div className="flex flex-wrap justify-center gap-2">
                {["OpenAI", "SpaceX launches", "Global chip shortage", "Brexit negotiations", "Covid-19 pandemic"].map((q) => (
                  <button 
                    key={q}
                    onClick={() => handleSearch(q)}
                    className={`px-4 py-2 rounded-full text-sm font-medium transition-colors border shadow-sm ${isDarkMode ? 'bg-slate-800 border-slate-700 text-slate-200 hover:bg-slate-700 hover:text-white' : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50 hover:text-slate-900 hover:border-slate-300'}`}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
            
          </div>
        </div>
      )}

      {isLoading && !timeline ? (
        <div className="flex flex-col justify-center items-center py-32 space-y-4">
          <div className={`animate-spin rounded-full h-8 w-8 border-b-2 ${isDarkMode ? 'border-slate-100' : 'border-slate-900'}`}></div>
          <div className={`font-medium animate-pulse ${isDarkMode ? 'text-slate-300' : 'text-slate-600'}`}>{progressMsg}</div>
        </div>
      ) : (
        <main className="flex-1 flex flex-col pt-10">
          {viewTimeline && timeline && timeline.length > 0 && (
            <div id="timeline" className="scroll-mt-24">
              <TimelineSummary timeline={timeline} isDarkMode={isDarkMode} />
              <TimelineFeed timeline={timeline} isDarkMode={isDarkMode} />
            </div>
          )}

          {viewTimeline && timeline && timeline.length === 0 && progressMsg !== "Generating chronological timeline..." && (
            <div className={`text-center py-20 ${isDarkMode ? 'text-slate-400' : 'text-slate-500'}`}>No events found.</div>
          )}

          {isLoading && timeline && (
            <div className="flex justify-center items-center py-12 space-x-3 opacity-70">
              <div className={`animate-spin rounded-full h-5 w-5 border-b-2 ${isDarkMode ? 'border-slate-100' : 'border-slate-700'}`}></div>
              <span className={`text-sm font-medium ${isDarkMode ? 'text-slate-300' : 'text-slate-600'}`}>Streaming chronological events...</span>
            </div>
          )}

          {isFeedbackOpen && (
            <FeedbackPanel
              onSubmit={handleFeedbackSubmit}
              isSubmitting={isSubmittingFeedback}
              status={feedbackStatus}
              onClose={() => setIsFeedbackOpen(false)}
              isDarkMode={isDarkMode}
            />
          )}

          <Footer
            onOpenFeedback={() => setIsFeedbackOpen(true)}
            onNavigateHome={handleNavigateHome}
            homeLabel={hasTimelineCache ? (viewTimeline ? "Home" : "Timeline") : "Home"}
            isDarkMode={isDarkMode}
            onToggleDarkMode={() => setIsDarkMode(prev => !prev)}
            isHomeDisabled={isLoading || isTracing}
            onToggleRetrieval={() => setShowRetrieval(prev => !prev)}
            showRetrieval={showRetrieval}
            retrieverOnline={retrieverOnline}
          />
        </main>
      )}
      {/* Retrieval Trace Sidebar */}
      <AnimatePresence>
        {showRetrieval && (
          <motion.aside
            initial={{ x: 300, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 300, opacity: 0 }}
            transition={{ type: 'tween', duration: 0.25 }}
            className={`fixed right-4 top-20 bottom-4 w-96 z-50 rounded-2xl shadow-2xl overflow-hidden flex flex-col ${isDarkMode ? 'bg-slate-900 border border-slate-800 text-slate-100' : 'bg-white border border-slate-100 text-slate-900'}`}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b shrink-0" style={{borderColor: isDarkMode ? 'rgba(148,163,184,0.06)' : 'rgba(2,6,23,0.04)'}}>
              <div className="font-semibold">View Sources</div>
              <div className="flex items-center gap-2">
                <div className="text-xs text-slate-400">{sortedRetrievalArticles ? sortedRetrievalArticles.length : 0} articles</div>
                <button onClick={() => setShowRetrieval(false)} className={`px-3 py-1 rounded-full text-sm ${isDarkMode ? 'bg-slate-800 text-slate-200' : 'bg-slate-100 text-slate-700'}`}>Close</button>
              </div>
            </div>
            
            {sortedRetrievalArticles && sortedRetrievalArticles.length > 0 && (
              <div className="px-4 py-2 border-b flex items-center justify-between shrink-0" style={{borderColor: isDarkMode ? 'rgba(148,163,184,0.06)' : 'rgba(2,6,23,0.04)'}}>
                <span className={`text-xs font-medium ${isDarkMode ? 'text-slate-400' : 'text-slate-500'}`}>Sort by:</span>
                <div className={`flex rounded-lg overflow-hidden border ${isDarkMode ? 'border-slate-700' : 'border-slate-200'}`}>
                  <button 
                    onClick={() => setSortSourcesBy('similarity')} 
                    className={`px-3 py-1 text-xs font-medium transition-colors ${sortSourcesBy === 'similarity' ? (isDarkMode ? 'bg-slate-700 text-white' : 'bg-slate-200 text-slate-900') : (isDarkMode ? 'bg-slate-900 text-slate-400 hover:bg-slate-800' : 'bg-white text-slate-600 hover:bg-slate-50')}`}
                  >
                    Similarity
                  </button>
                  <button 
                    onClick={() => setSortSourcesBy('newest')} 
                    className={`px-3 py-1 text-xs font-medium transition-colors border-l ${isDarkMode ? 'border-slate-700' : 'border-slate-200'} ${sortSourcesBy === 'newest' ? (isDarkMode ? 'bg-slate-700 text-white' : 'bg-slate-200 text-slate-900') : (isDarkMode ? 'bg-slate-900 text-slate-400 hover:bg-slate-800' : 'bg-white text-slate-600 hover:bg-slate-50')}`}
                  >
                    Newest
                  </button>
                  <button 
                    onClick={() => setSortSourcesBy('oldest')} 
                    className={`px-3 py-1 text-xs font-medium transition-colors border-l ${isDarkMode ? 'border-slate-700' : 'border-slate-200'} ${sortSourcesBy === 'oldest' ? (isDarkMode ? 'bg-slate-700 text-white' : 'bg-slate-200 text-slate-900') : (isDarkMode ? 'bg-slate-900 text-slate-400 hover:bg-slate-800' : 'bg-white text-slate-600 hover:bg-slate-50')}`}
                  >
                    Oldest
                  </button>
                </div>
              </div>
            )}

            <div className="p-3 overflow-y-auto flex-1">
              {!sortedRetrievalArticles && (
                <div className="p-4 text-sm text-slate-500">No sources available.</div>
              )}
              {sortedRetrievalArticles && sortedRetrievalArticles.length > 0 && (
                <div className="space-y-3 pb-20">
                  {sortedRetrievalArticles.map((a, i) => (
                    <a key={i} href={a.url} target="_blank" rel="noreferrer" className="block p-3 rounded-xl hover:shadow-md transition-colors">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1">
                          <div className="text-sm font-semibold line-clamp-2">{a.title}</div>
                          <div className="text-xs text-slate-400 mt-1">{a.date}</div>
                        </div>
                        <div className="ml-3 flex-shrink-0">
                          <div className={`text-xs font-medium px-2 py-0.5 rounded-full ${isDarkMode ? 'bg-slate-800 text-sky-300' : 'bg-slate-100 text-slate-800'}`}>{(a.score||0).toFixed(3)}</div>
                        </div>
                      </div>
                      {a.description && <div className="text-xs mt-2 text-slate-500 line-clamp-3">{a.description}</div>}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  );
};

// Mount App
const rootElement = document.getElementById('root');
const root = ReactDOM.createRoot(rootElement);
root.render(<App />);
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
  const date = new Date(dateStr);
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

const SearchPanel = ({ onSearch, isLoading }) => {
  const [query, setQuery] = useLocalStorage('newsTrace_query', '');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim()) {
      onSearch(query);
    }
  };

  return (
    <div className="sticky top-0 z-50 py-6 px-4 bg-slate-50/80 backdrop-blur-md border-b border-slate-200 shadow-sm">
      <div className="max-w-4xl mx-auto flex items-center gap-6">
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight hidden sm:block">NewsTrace</h1>
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
              placeholder="Search chronological timeline..."
              className="w-full pl-12 pr-4 py-3 rounded-full bg-white border border-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-all disabled:opacity-50 disabled:bg-slate-100"
            />
            <button 
              type="submit" 
              disabled={isLoading || !query.trim()}
              className="absolute right-2 px-6 py-1.5 bg-slate-900 text-white rounded-full text-sm font-medium hover:bg-slate-800 disabled:opacity-50 transition-colors"
            >
              {isLoading ? "Searching..." : "Trace"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

const NewsCard = ({ event }) => {
  const [expanded, setExpanded] = useState(false);
  const [showAllSources, setShowAllSources] = useState(false);
  
  const hasSubEvents = event.sub_events && event.sub_events.length > 0;
  const isMajor = event.type === 'major_event';

  return (
    <div className={`relative bg-white rounded-2xl shadow-sm border hover:shadow-md transition-all group ${isMajor ? 'p-6 border-blue-100 ring-1 ring-blue-50' : 'p-4 border-slate-200'}`}>
      <div className={`flex justify-between items-start ${isMajor ? 'mb-3' : 'mb-2'}`}>
        <div>
          {isMajor && (
            <span className="inline-block px-2.5 py-1 bg-red-100 text-red-700 text-xs font-semibold rounded-md mb-2 tracking-wide uppercase shadow-sm">
              Major Event
            </span>
          )}
          <div className="text-sm font-medium text-slate-500 mb-1">{event.date}</div>
        </div>
      </div>
      
      <h3 className={`font-semibold text-slate-900 ${isMajor ? 'text-xl mb-2' : 'text-lg mb-1.5'}`}>{event.headline}</h3>
      <p 
        className={`text-slate-600 leading-relaxed ${isMajor ? 'mb-4 text-base' : 'mb-3 text-sm line-clamp-2'}`}
        title={!isMajor ? event.summary : undefined}
      >
        {event.summary}
      </p>

      {/* Sources list */}
      {event.sources && event.sources.length > 0 && (
        <div className={`flex flex-wrap gap-2 ${hasSubEvents ? 'mb-4' : 'mb-1'}`}>
          <span className="text-xs text-slate-400 my-auto uppercase tracking-wide font-medium">Sources:</span>
          {(showAllSources ? event.sources : event.sources.slice(0, 3)).map((url, i) => {
            try { 
              const domain = new URL(url).hostname.replace('www.', '');
              return (
                <a key={i} href={url} target="_blank" rel="noopener noreferrer" className="text-xs px-2 py-1 bg-slate-100 text-blue-600 hover:text-white hover:bg-blue-500 transition-colors rounded-md">
                  {domain}
                </a>
              );
            } catch { return null; }
          })}
          {!showAllSources && event.sources.length > 3 && (
            <button 
              onClick={() => setShowAllSources(true)} 
              className="text-xs px-2 py-1 bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors rounded-md"
            >
              +{event.sources.length - 3} more
            </button>
          )}
          {showAllSources && event.sources.length > 3 && (
            <button 
              onClick={() => setShowAllSources(false)} 
              className="text-xs px-2 py-1 bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors rounded-md"
            >
              Show less
            </button>
          )}
        </div>
      )}

      {hasSubEvents && (
        <div className="mt-4 pt-4 border-t border-slate-100">
          <button 
            onClick={() => setExpanded(!expanded)}
            className="flex items-center justify-between w-full text-sm font-medium text-slate-700 hover:text-blue-600 transition-colors"
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
                <div className="pt-4 pl-4 border-l-2 border-dashed border-slate-300 ml-2 mt-2 space-y-4">
                  {event.sub_events.map((sub, i) => (
                    <div key={i} className="relative">
                      {/* Dashed connector line horizontal stub */}
                      <div className="absolute -left-4 top-2.5 w-3 border-t-2 border-dashed border-slate-300"></div>
                      {sub.date && <div className="text-xs text-slate-500 mb-0.5">{sub.date}</div>}
                      <h4 className="text-sm font-semibold text-slate-800">{sub.headline}</h4>
                      <p className="text-sm text-slate-600 mt-1">{sub.summary}</p>
                      {sub.url && (
                        <a href={sub.url} target="_blank" rel="noopener noreferrer" className="inline-block mt-2 text-xs font-semibold text-blue-600 hover:text-blue-800 transition-colors">
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

const TimelineSummary = ({ timeline }) => {
  const majorEvents = timeline.filter(event => event.type === "major_event");

  if (majorEvents.length === 0) return null;

  return (
    <div className="max-w-5xl mx-auto mt-6 px-4">
      <div className="bg-white/70 backdrop-blur-xl border border-slate-200 shadow-sm rounded-xl p-5">
        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-widest mb-4 flex items-center gap-2">
          <span>Major Events Summary</span>
          <span className="bg-slate-900 text-white text-[10px] px-2 py-0.5 rounded-full">{majorEvents.length}</span>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {majorEvents.map((event) => (
            <a 
              key={event.id}
              href={`#${event.id}`}
              className="group block p-3 rounded-lg bg-slate-50 hover:bg-blue-50 border border-slate-100 hover:border-blue-200 transition-all text-left"
            >
              <div className="text-xs font-semibold text-blue-600 mb-1">{event.date}</div>
              <div className="text-sm font-medium text-slate-800 group-hover:text-blue-900 line-clamp-2 leading-snug">
                {event.headline}
              </div>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
};

const TimelineFeed = ({ timeline }) => {
  const groupedTimeline = useMemo(() => groupEventsByMonth(timeline), [timeline]);

  return (
    <div className="max-w-5xl mx-auto py-12 px-4">
      {groupedTimeline.map(([monthYear, events]) => (
        <div key={monthYear} className="relative mb-16">
          {/* Sticky Month Header */}
          <div className="sticky top-[104px] z-40 flex justify-center mb-8 pointer-events-none">
            <div className="bg-slate-900/90 backdrop-blur text-white px-6 py-2 rounded-full font-medium shadow-md shadow-slate-900/10 pointer-events-auto">
              {monthYear}
            </div>
          </div>

          <div className="relative">
            {/* The Central Spine */}
            <div className="absolute left-4 md:left-1/2 transform md:-translate-x-1/2 top-0 bottom-0 flex justify-center w-6 md:w-8">
              <div className="h-full w-0.5 bg-slate-200"></div>
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
                        <NewsCard event={event} />
                      </div>
                    </div>

                    {/* Connector line (desktop only) */}
                    <div className={`hidden md:block absolute top-1/2 transform -translate-y-1/2 ${isLeft ? 'right-1/2 mr-8' : 'left-1/2 ml-8'} w-8 border-t-2 border-dashed border-slate-300 z-0`}></div>
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

const App = () => {
  const [timeline, setTimeline] = useLocalStorage('newsTrace_timeline', null);
  const [query, setQuery] = useLocalStorage('newsTrace_query', '');
  const [isTracing, setIsTracing] = useLocalStorage('newsTrace_isTracing', false);
  const [progressMsg, setProgressMsg] = useState("Initializing trace...");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isTracing && query) {
      handleSearch(query, true);
    }
  }, []); // Run once on mount

  const handleSearch = (searchQuery, isResume = false) => {
    setIsLoading(true);
    setError(null);
    
    // If not resuming, we reset the timeline and update query
    if (!isResume) {
      setTimeline(null); 
      setQuery(searchQuery);
    }
    setIsTracing(true);
    setProgressMsg(isResume ? "Resuming trace..." : "Connecting to server...");

    // Replace this string with your Ngrok or Cloudflare Tunnel URL when deploying.
    // e.g., const API_BASE_URL = "https://1234-abcd.ngrok-free.app";
    const API_BASE_URL = " https://situation-degrease-flavorful.ngrok-free.dev";
    const eventSource = new EventSource(`${API_BASE_URL}/api/news?query=${encodeURIComponent(searchQuery)}`);
    
    // We need to deduplicate events if we are resuming, because the server replays all events.
    // An easy way is to clear the timeline right as we receive the first actual event from the server.
    let hasClearedForReplay = !isResume; 

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "progress") {
          setProgressMsg(data.message);
        } else {
          data.id = `event-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
          setTimeline(prev => {
            // First time we get an event on this connection, if it's a resume replay, clear old items
            if (!hasClearedForReplay) {
              hasClearedForReplay = true;
              return [data];
            }
            return [...(Array.isArray(prev) ? prev : []), data];
          });
        }
      } catch (err) {
        console.error("Error parsing streaming data", err);
      }
    };

    eventSource.addEventListener('close', () => {
      eventSource.close();
      setIsLoading(false);
      setIsTracing(false);
    });

    eventSource.onerror = (err) => {
      eventSource.close();
      setIsLoading(false);
      setIsTracing(false);
      setTimeline(prev => {
        if (!prev || prev.length === 0) setError("Failed to fetch data or connection closed.");
        return prev;
      });
    };
  };

  // If there's no data initialized but we just landed, we won't show anything 
  // until the user presses trace.

  return (
    <div className="min-h-screen relative">
      <SearchPanel onSearch={handleSearch} isLoading={isLoading} />
      
      {error && (
        <div className="max-w-4xl mx-auto mt-8 p-4 bg-red-50 border border-red-200 text-red-700 rounded-xl shadow-sm text-center">
          <p className="font-semibold">Error Loading Trace</p>
          <p className="text-sm opacity-80">{error}</p>
        </div>
      )}
      
      {!isLoading && !timeline && progressMsg && progressMsg !== "Initializing trace..." && progressMsg !== "Connecting to server..." && !error && (
        <div className="max-w-4xl mx-auto mt-8 p-4 bg-orange-50 border border-orange-200 text-orange-800 rounded-xl shadow-sm text-center">
          <p className="font-semibold">Notice</p>
          <p className="text-sm opacity-90">{progressMsg}</p>
        </div>
      )}

      {/* First-Time User Introduction */}
      {!isLoading && !timeline && (!progressMsg || progressMsg === "Initializing trace...") && !error && (
        <div className="max-w-4xl mx-auto mt-16 px-4 md:px-0 opacity-0 animate-[fadeIn_0.5s_ease-out_forwards]">
          <div className="bg-white/80 backdrop-blur-sm rounded-3xl shadow-lg border border-slate-200 p-8 md:p-12 text-center text-slate-800">
            <div className="w-16 h-16 mx-auto mb-6 bg-gradient-to-tr from-blue-500 to-indigo-500 rounded-2xl flex items-center justify-center shadow-md text-white">
              <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9.5a2.5 2.5 0 00-2.5-2.5H15M9 11l3 3L22 4" />
              </svg>
            </div>
            <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight mb-4 text-slate-900">
              Welcome to NewsTrace
            </h2>
            <p className="text-lg md:text-xl text-slate-600 mb-10 max-w-2xl mx-auto leading-relaxed">
              Discover the full story behind the headlines. Enter a topic, company, or global event to instantly generate a comprehensive, AI-powered chronological timeline compiled from verified news sources.
            </p>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-left mb-8">
              <div className="bg-slate-50 p-6 rounded-2xl border border-slate-100 transition hover:shadow-md hover:-translate-y-1 duration-300">
                <div className="text-xl mb-3">🔍</div>
                <h3 className="font-bold text-slate-900 mb-2">1. Ask Anything</h3>
                <p className="text-sm text-slate-600 leading-relaxed">Search for complex global events, historical milestones, or specific companies (e.g., "The rise of AI model tech").</p>
              </div>
              <div className="bg-slate-50 p-6 rounded-2xl border border-slate-100 transition hover:shadow-md hover:-translate-y-1 duration-300">
                <div className="text-xl mb-3">🧠</div>
                <h3 className="font-bold text-slate-900 mb-2">2. AI Analysis</h3>
                <p className="text-sm text-slate-600 leading-relaxed">Our backend semantic search isolates thousands of articles while the LLM categorizes and verifies key events.</p>
              </div>
              <div className="bg-slate-50 p-6 rounded-2xl border border-slate-100 transition hover:shadow-md hover:-translate-y-1 duration-300">
                <div className="text-xl mb-3">⚡</div>
                <h3 className="font-bold text-slate-900 mb-2">3. Track the Trace</h3>
                <p className="text-sm text-slate-600 leading-relaxed">Watch your custom timeline stream onto the page in real-time, complete with impact tracking and native citations.</p>
              </div>
            </div>
            
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-blue-50 text-blue-700 rounded-full text-xs font-medium border border-blue-100">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Note: The indexed dataset spans securely from January 2016 to May 2026.
            </div>
          </div>
        </div>
      )}

      {isLoading && !timeline ? (
        <div className="flex flex-col justify-center items-center py-32 space-y-4">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900"></div>
            <div className="text-slate-600 font-medium animate-pulse">{progressMsg}</div>
        </div>
      ) : (
        <>
          {timeline && <TimelineSummary timeline={timeline} />}
          {timeline && timeline.length > 0 && <TimelineFeed timeline={timeline} />}
          {isLoading && timeline && (
            <div className="flex justify-center items-center py-12 space-x-3 opacity-70">
               <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-slate-700"></div>
               <span className="text-sm text-slate-600 font-medium">Streaming chronological events...</span>
            </div>
          )}
          {!isLoading && timeline && timeline.length === 0 && (
            <div className="text-center py-20 text-slate-500">No events found.</div>
          )}
        </>
      )}
    </div>
  );
};

// Mount App
const rootElement = document.getElementById('root');
const root = ReactDOM.createRoot(rootElement);
root.render(<App />);
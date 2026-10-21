import React, { useEffect, useId, useRef } from "react";

export default function PageTabs({ label, tabs, value, onChange, children }) {
  const id = useId();
  const buttons = useRef({});
  useEffect(() => {
    buttons.current[value]?.scrollIntoView({
      block: "nearest",
      inline: "nearest",
    });
  }, [value]);
  function move(event, index) {
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft")
      next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    onChange(tabs[next].id);
    buttons.current[tabs[next].id]?.focus();
  }
  return (
    <div className="page-tabs">
      <div className="page-tab-list" role="tablist" aria-label={label}>
        {tabs.map(({ id: tab, label: title, icon: Icon }, index) => (
          <button
            key={tab}
            ref={(button) => {
              buttons.current[tab] = button;
            }}
            type="button"
            role="tab"
            id={`${id}-${tab}`}
            aria-selected={value === tab}
            aria-controls={`${id}-panel`}
            tabIndex={value === tab ? 0 : -1}
            onClick={() => onChange(tab)}
            onKeyDown={(event) => move(event, index)}
          >
            {Icon && <Icon size={17} aria-hidden="true" />}
            {title}
          </button>
        ))}
      </div>
      <div
        className="page-tab-panel"
        id={`${id}-panel`}
        role="tabpanel"
        aria-labelledby={`${id}-${value}`}
        tabIndex={0}
      >
        {children}
      </div>
    </div>
  );
}

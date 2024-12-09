"use client"; // Marking the component as Client Component

import React, { useState } from "react";
import { Sidebar } from "../sidebar/page";
import { FiCheckCircle } from "react-icons/fi";
import { FaUserCircle } from "react-icons/fa"; // User icon for user messages
import { FaRobot } from "react-icons/fa"; // Replacing with robot icon for bot

export default function FitnessAssistant() {
  const [messages, setMessages] = useState<
    { type: "user" | "bot"; content: string; timestamp: string }[]
  >([]);
  const [userInput, setUserInput] = useState("");

  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleSend = () => {
    if (!userInput.trim()) return;

    const timestamp = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });

    setMessages((prev) => [
      ...prev,
      { type: "user", content: userInput, timestamp },
    ]);

    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          type: "bot",
          content: `Here’s an exercise tailored for "${userInput}"!`,
          timestamp,
        },
      ]);
    }, 1000);

    setUserInput("");
  };

  // Handle pressing 'Enter' to send a message
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      handleSend();
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-gray-200 flex overflow-hidden">
      {" "}
      {/* Main container */}
      {/* Sidebar */}
      <Sidebar sidebarOpen={sidebarOpen} setSidebarOpen={setSidebarOpen} />
      {/* Main Content */}
      <div
        className={`flex-grow transition-all duration-300 ${
          sidebarOpen ? "ml-64" : "ml-0"
        }`}
      >
        <div className="flex flex-col items-center justify-center min-h-screen w-full px-8">
          <div className="w-2/3 max-w-full bg-slate-950 p-8 rounded-lg">
            {/* Header */}
            <div className="text-center text-4xl font-semibold text-gray-100 tracking-wide">
              Fitness Assistant
            </div>
            {/* Marketable Description */}
            <div className="text-center text-lg font-medium text-gray-600 mb-4 p-4">
              <p>Welcome to Your Fitness Assistant!</p>
              <p>
                Discover personalized exercises and nutrition tips 🤖 just for
                YOU!
              </p>
              <p>
                Curious about the nutrition of any food? 🍎🥦 Ask now and fuel
                your goals!
              </p>
            </div>

            {/* Chat Area */}
            <div className="h-[55vh] overflow-y-auto p-6 space-y-6 bg-slate-950 w-full max-w-full">
              {messages.length === 0 && (
                <p className="text-center text-gray-500 italic">
                  Ready to level up your fitness journey? 🚀 Let's get started!
                </p>
              )}
              {messages.map((message, index) => (
                <div
                  key={index}
                  className={`flex items-start gap-2 ${
                    message.type === "user" ? "flex-row-reverse" : "flex-row"
                  }`}
                >
                  {/* Icon */}
                  {message.type === "user" ? (
                    <FaUserCircle className="text-[#7a73c1] text-3xl" />
                  ) : (
                    <FaRobot className="text-gray-400 text-3xl" />
                  )}

                  {/* Message */}
                  <div className="flex flex-col max-w-full">
                    <div
                      className={`max-w-[85%] px-4 py-2 rounded-lg text-lg break-words ${
                        message.type === "user"
                          ? "bg-gradient-to-r from-[#7a73c1] to-[#7a73c1] text-white"
                          : "bg-gray-800 text-gray-300"
                      } shadow-sm hover:shadow-lg transition-shadow`}
                    >
                      {message.content}
                    </div>
                    {/* Metadata */}
                    <div className="flex items-center gap-2 mt-1 text-gray-400 text-xs">
                      <span>{message.timestamp}</span>
                      {message.type === "user" && (
                        <FiCheckCircle className="text-green-500" />
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="p-3 bg-slate-950 flex gap-2 items-center w-full">
              <input
                type="text"
                placeholder="Ask me for fitness recommendations..."
                value={userInput}
                onChange={(e) => setUserInput(e.target.value)}
                onKeyDown={handleKeyDown} // Trigger the send function on 'Enter'
                className="w-full p-2 text-sm rounded-md text-gray-900 bg-gray-200 focus:outline-none focus:ring-2 focus:ring-[#7a73c1] overflow-hidden text-ellipsis"
              />
              <button
                onClick={handleSend}
                className="px-4 py-2 text-sm bg-[#42499b] text-white rounded-md hover:bg-[#42499b] transition-all"
              >
                Send
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

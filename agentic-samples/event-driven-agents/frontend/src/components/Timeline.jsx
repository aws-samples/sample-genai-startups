import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Brain,
  Search,
  FileText,
  UserCheck,
  CheckCircle,
  Clock,
  Loader2,
  Activity
} from 'lucide-react';

const TOOL_ICONS = {
  'searchAgent': Search,
  'generatePDF': FileText,
  'humanReviewer': UserCheck,
  'documentQuerier': FileText,
  'default': Activity
};

const Timeline = ({ events = [], isAnalyzing = false }) => {
  if (!isAnalyzing && events.length === 0) {
    return null;
  }

  const getToolIcon = (toolName) => {
    return TOOL_ICONS[toolName] || TOOL_ICONS.default;
  };

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  return (
    <Card className="mb-6 border-blue-200 bg-blue-50/30">
      <CardContent className="p-6">
        <div className="flex items-center space-x-2 mb-4">
          <Brain className="h-5 w-5 text-blue-600" />
          <h3 className="font-semibold text-blue-900">AI Processing Timeline</h3>
        </div>
        
        <div className="space-y-3">

          {/* Tool execution events */}
          {events.map((event, index) => {
            const ToolIcon = event.toolName === 'thinking' ? Brain : getToolIcon(event.toolName);
            const isActive = event.status === 'in_progress';
            
            return (
              <div key={event.id || `${event.toolName}-${index}`} className="flex items-center space-x-3 p-3 bg-white rounded-lg border border-blue-100">
                <div className="flex-shrink-0">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                    isActive 
                      ? 'bg-yellow-100 border-2 border-yellow-300' 
                      : 'bg-blue-100'
                  }`}>
                    {isActive ? (
                      <Loader2 className="h-4 w-4 text-yellow-600 animate-spin" />
                    ) : (
                      <ToolIcon className="h-4 w-4 text-blue-600" />
                    )}
                  </div>
                </div>
                <div className="flex-1">
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-medium text-gray-900">
                      {event.message}
                    </span>
                    <Badge 
                      variant={isActive ? "default" : "secondary"} 
                      className={`text-xs ${isActive ? 'bg-yellow-100 text-yellow-800 border-yellow-300' : ''}`}
                    >
                      {event.status === 'in_progress' ? 'In Progress' : 'Completed'}
                    </Badge>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {formatTimestamp(event.timestamp)}
                    {event.toolName !== 'thinking' && ` • Tool: ${event.toolName}`}
                  </div>
                </div>
                <div className="flex-shrink-0">
                  {isActive ? (
                    <Clock className="h-4 w-4 text-yellow-500" />
                  ) : (
                    <CheckCircle className="h-4 w-4 text-green-500" />
                  )}
                </div>
              </div>
            );
          })}

        </div>
      </CardContent>
    </Card>
  );
};

export default Timeline;
"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface QuizQuestion {
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
  difficulty: string;
}

interface QuizModalProps {
  isOpen: boolean;
  onClose: () => void;
  unitTitle: string;
  questions: QuizQuestion[];
  totalXp: number;
  onSubmit: (answers: number[]) => Promise<{
    scorePct: number;
    correctCount: number;
    xpEarned: number;
  }>;
}

export function QuizModal({
  isOpen,
  onClose,
  unitTitle,
  questions,
  totalXp,
  onSubmit,
}: QuizModalProps) {
  const [currentQuestion, setCurrentQuestion] = React.useState(0);
  const [answers, setAnswers] = React.useState<number[]>([]);
  const [selectedAnswer, setSelectedAnswer] = React.useState<number | null>(
    null
  );
  const [showResult, setShowResult] = React.useState(false);
  const [result, setResult] = React.useState<{
    scorePct: number;
    correctCount: number;
    xpEarned: number;
  } | null>(null);
  const [showExplanation, setShowExplanation] = React.useState(false);

  if (!isOpen) return null;

  const question = questions[currentQuestion];
  const isLastQuestion = currentQuestion === questions.length - 1;
  const hasAnswered = selectedAnswer !== null;

  const handleSelectAnswer = (index: number) => {
    if (showExplanation) return;
    setSelectedAnswer(index);
  };

  const handleConfirmAnswer = () => {
    if (selectedAnswer === null) return;

    const newAnswers = [...answers, selectedAnswer];
    setAnswers(newAnswers);
    setShowExplanation(true);
  };

  const handleNextQuestion = async () => {
    if (isLastQuestion) {
      const finalAnswers = [...answers];
      const submitResult = await onSubmit(finalAnswers);
      setResult(submitResult);
      setShowResult(true);
    } else {
      setCurrentQuestion(currentQuestion + 1);
      setSelectedAnswer(null);
      setShowExplanation(false);
    }
  };

  const handleClose = () => {
    setCurrentQuestion(0);
    setAnswers([]);
    setSelectedAnswer(null);
    setShowResult(false);
    setResult(null);
    setShowExplanation(false);
    onClose();
  };

  const getDifficultyColor = (difficulty: string) => {
    switch (difficulty) {
      case "recall":
        return "text-blue-500";
      case "understanding":
        return "text-green-500";
      case "connection":
        return "text-purple-500";
      case "analysis":
        return "text-orange-500";
      default:
        return "text-gray-500";
    }
  };

  if (showResult && result) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
        <Card className="w-full max-w-md mx-4 animate-in fade-in zoom-in">
          <CardHeader className="text-center">
            <CardTitle className="text-2xl">
              {result.scorePct >= 80
                ? "Excellent! 🎉"
                : result.scorePct >= 60
                ? "Good job! 👍"
                : "Keep practicing! 📚"}
            </CardTitle>
            <CardDescription>Quiz Complete: {unitTitle}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="text-center">
              <div className="text-5xl font-bold text-primary">
                {result.scorePct.toFixed(0)}%
              </div>
              <p className="text-muted-foreground">
                {result.correctCount} of {questions.length} correct
              </p>
            </div>
            <div className="flex items-center justify-center gap-2 p-4 rounded-lg bg-gradient-to-r from-purple-50 to-pink-50 dark:from-purple-950/20 dark:to-pink-950/20">
              <span className="text-2xl">✨</span>
              <span className="text-xl font-bold text-purple-600">
                +{result.xpEarned} XP
              </span>
            </div>
          </CardContent>
          <CardFooter>
            <Button onClick={handleClose} className="w-full">
              Continue Reading
            </Button>
          </CardFooter>
        </Card>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <Card className="w-full max-w-lg mx-4 animate-in fade-in zoom-in">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">Comprehension Check</CardTitle>
            <span className="text-sm text-muted-foreground">
              {currentQuestion + 1} / {questions.length}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "text-xs font-medium capitalize",
                getDifficultyColor(question.difficulty)
              )}
            >
              {question.difficulty}
            </span>
            <span className="text-xs text-muted-foreground">
              • {totalXp} XP available
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-base font-medium">{question.question}</p>
          <div className="space-y-2">
            {question.options.map((option, index) => {
              const isSelected = selectedAnswer === index;
              const isCorrect = index === question.correct_index;
              const showCorrectness = showExplanation;

              return (
                <button
                  key={index}
                  onClick={() => handleSelectAnswer(index)}
                  disabled={showExplanation}
                  className={cn(
                    "w-full p-3 text-left rounded-lg border transition-all",
                    "hover:border-primary/50 hover:bg-accent",
                    isSelected && !showCorrectness && "border-primary bg-primary/5",
                    showCorrectness &&
                      isCorrect &&
                      "border-green-500 bg-green-50 dark:bg-green-950/20",
                    showCorrectness &&
                      isSelected &&
                      !isCorrect &&
                      "border-red-500 bg-red-50 dark:bg-red-950/20"
                  )}
                >
                  {option}
                </button>
              );
            })}
          </div>
          {showExplanation && (
            <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800">
              <p className="text-sm">
                <span className="font-medium">Explanation: </span>
                {question.explanation}
              </p>
            </div>
          )}
        </CardContent>
        <CardFooter className="flex justify-between">
          <Button variant="outline" onClick={handleClose}>
            Exit Quiz
          </Button>
          {!showExplanation ? (
            <Button onClick={handleConfirmAnswer} disabled={!hasAnswered}>
              Confirm Answer
            </Button>
          ) : (
            <Button onClick={handleNextQuestion}>
              {isLastQuestion ? "See Results" : "Next Question"}
            </Button>
          )}
        </CardFooter>
      </Card>
    </div>
  );
}

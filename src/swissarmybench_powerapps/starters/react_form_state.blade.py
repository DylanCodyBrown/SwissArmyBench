# /// swissarmybench-blade
# format = 1
# name = "Form with state"
# kind = "snippet"
# description = "A form of controlled inputs: its values in state, checked on submit, handed to the page when right"
# tags = ["react", "tsx", "form", "code app"]
# family = "React"
# language = "tsx"
# ///
snippet = r"""

import { useState, type FormEvent } from "react";

interface Values {
  name: string;
  email: string;
}

// A form whose inputs it keeps itself (controlled), checked before it hands the values on.
export function <<component name: ContactForm>>({ onSubmit }: { onSubmit: (values: Values) => void }) {
  const [values, setValues] = useState<Values>({ name: "", email: "" });
  const [problem, setProblem] = useState<string | null>(null);
  const change = (key: keyof Values) => (e: { target: { value: string } }) => setValues({ ...values, [key]: e.target.value });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!values.name.trim()) return setProblem("A name, please.");
    setProblem(null);
    onSubmit(values);
  };
  return (
    <form onSubmit={submit}>
      <label>Name <input value={values.name} onChange={change("name")} /></label>
      <label>Email <input type="email" value={values.email} onChange={change("email")} /></label>
      {problem && <p role="alert">{problem}</p>}
      <button type="submit">{"<<button text: Save>>"}</button>
    </form>
  );
}
"""

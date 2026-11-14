// Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
// SAMPLE MEDICATION PLAN for the Crew Medical Officer view (doctor.html).
// Illustrative demo data, NOT medical guidance. Nothing in the backend or
// docs/api-spec.md describes medications yet; a real plan would come from a
// backend endpoint (requested in STATUS.md). Times are station time (UTC).
//
// Each entry is a daily dose. `onAlert` lists what the Crew Medical Officer
// might consider when an alert arrives; it is a prompt for their judgement,
// never an instruction.

window.AHM_MEDS = {
  schedule: [
    // Every crew member: no sunlight in flight, so vitamin D is supplemented.
    { aid: "a1", drug: "Vitamin D3", dose: "800 IU", route: "oral", times: ["08:00"], purpose: "Bone health (no sunlight in flight)" },
    { aid: "a2", drug: "Vitamin D3", dose: "800 IU", route: "oral", times: ["08:00"], purpose: "Bone health (no sunlight in flight)" },
    { aid: "a3", drug: "Vitamin D3", dose: "800 IU", route: "oral", times: ["08:00"], purpose: "Bone health (no sunlight in flight)" },
    { aid: "a4", drug: "Vitamin D3", dose: "800 IU", route: "oral", times: ["08:00"], purpose: "Bone health (no sunlight in flight)" },

    { aid: "a1", drug: "Vitamin B complex", dose: "1 tablet", route: "oral", times: ["14:00"],
      purpose: "SANS countermeasure under investigation (study participant)" },
    { aid: "a2", drug: "Melatonin", dose: "3 mg", route: "oral", times: ["22:00"],
      purpose: "Sleep timing (irregular bedtimes this week)" },
    { aid: "a3", drug: "Oxymetazoline nasal spray", dose: "1 spray per nostril", route: "nasal", times: ["07:00", "19:00"],
      purpose: "Congestion from headward fluid shift (max 3 days)" },
    { aid: "a4", drug: "Ibuprofen", dose: "400 mg", route: "oral, with food", times: ["12:00", "20:00"],
      purpose: "Lower-back pain from spinal lengthening" },
  ],

  // Alert profile -> medication the CMO might consider.
  onAlert: {
    orthostatic: { drug: "Fluid loading: salt tablets + water", dose: "1 g salt, 500 ml water",
      note: "Before standing up; re-check in 10 min." },
    fever: { drug: "Paracetamol (acetaminophen)", dose: "500 mg",
      note: "Only if you agree after examining them." },
    sleep_debt: { drug: "Melatonin", dose: "3 mg",
      note: "Before the next sleep period, if you agree." },
  },
};

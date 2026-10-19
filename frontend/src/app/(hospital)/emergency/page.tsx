import React from "react";
import { AlertOctagon, ShieldAlert, FileWarning, CheckCircle } from "lucide-react";

export default function EmergencyAccessPage() {
  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Warning Header */}
      <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6 text-rose-900 space-y-2">
        <div className="flex items-center gap-2 font-bold text-rose-700 text-lg">
          <AlertOctagon className="w-6 h-6 text-rose-600" />
          Emergency "Break-Glass" Record Access
        </div>
        <p className="text-sm text-rose-800 leading-relaxed">
          This portal allows verified medical staff to access critical health records when patient OTP approval would delay emergency treatment.
        </p>
      </div>

      {/* Break-glass Form */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-6">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1">
              Patient ID
            </label>
            <input
              type="text"
              placeholder="MED-2026-XXXXXX"
              className="w-full px-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-rose-500 font-mono text-slate-900"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1">
              Emergency Triage Reason
            </label>
            <select className="w-full px-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-rose-500 text-slate-900 bg-white">
              <option value="">Select emergency clinical category...</option>
              <option value="unconscious_patient">Unconscious / Unresponsive Patient</option>
              <option value="trauma_resuscitation">Severe Trauma / Resuscitation</option>
              <option value="acute_cardiac_arrest">Acute Cardiac / Stroke Emergency</option>
              <option value="other_life_threatening">Other Immediate Life Threat</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1">
              Mandatory Clinical Justification Notes
            </label>
            <textarea
              rows={4}
              placeholder="Detail patient clinical status, presenting conditions, and reason why standard OTP verification cannot be performed..."
              className="w-full px-4 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-rose-500 text-slate-900"
            />
            <p className="text-[11px] text-slate-500 mt-1">Minimum 20 characters. Recorded in permanent hospital compliance log.</p>
          </div>
        </div>

        {/* Audit Disclaimer */}
        <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 text-xs text-slate-600 space-y-2">
          <div className="font-semibold text-slate-800 flex items-center gap-1.5">
            <ShieldAlert className="w-4 h-4 text-slate-600" /> Statutory Audit Notice
          </div>
          <p>
            By proceeding, you certify that this access is medically necessary under emergency triage protocols. The timestamp, your clinician ID, IP address, and hospital ID will be permanently recorded for institutional audit review.
          </p>
        </div>

        <button
          type="button"
          className="w-full py-3 bg-rose-600 hover:bg-rose-700 text-white font-semibold rounded-lg transition shadow-sm"
        >
          Authorize Emergency Break-Glass Access
        </button>
      </div>
    </div>
  );
}

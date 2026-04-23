import { Link } from "react-router";

interface Props {
  deviceTypeLabel: string;
  deviceTypeValue: string;
}

/**
 * Shared "No X devices yet" card used by the Vents / Trolley pages'
 * Test panel tab when no devices of that type are registered.
 */
export default function EmptyDevicesState({ deviceTypeLabel, deviceTypeValue }: Props) {
  return (
    <div className="col-span-full flex flex-col items-center justify-center p-16 border border-white/5 border-dashed rounded-3xl bg-zinc-900/20">
      <p className="text-zinc-300 text-lg font-medium">No {deviceTypeLabel} devices yet</p>
      <p className="text-zinc-500 text-sm mt-2">
        Add a device of type{" "}
        <span className="font-mono text-zinc-400">{deviceTypeValue}</span> on the{" "}
        <Link to="/devices" className="text-orange-400 hover:text-orange-300 underline">
          Devices
        </Link>{" "}
        page.
      </p>
    </div>
  );
}

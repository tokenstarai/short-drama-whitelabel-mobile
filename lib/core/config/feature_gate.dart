import 'package:flutter/widgets.dart';

class FeatureGate extends StatelessWidget {
  const FeatureGate({
    required this.enabled,
    required this.child,
    this.fallback = const SizedBox.shrink(),
    super.key,
  });

  final bool enabled;
  final Widget child;
  final Widget fallback;

  @override
  Widget build(BuildContext context) {
    return enabled ? child : fallback;
  }
}

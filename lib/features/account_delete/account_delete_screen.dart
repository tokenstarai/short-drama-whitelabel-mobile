import 'package:flutter/material.dart';

import '../../app/app_runtime.dart';
import '../../core/api/app_models.dart';
import '../../flavor/flavor.dart';

class AccountDeleteScreen extends StatefulWidget {
  const AccountDeleteScreen({required this.flavor, super.key});

  final FlavorConfig flavor;

  @override
  State<AccountDeleteScreen> createState() => _AccountDeleteScreenState();
}

class _AccountDeleteScreenState extends State<AccountDeleteScreen> {
  late final TextEditingController accountRefController;
  bool submitting = false;
  String? resultText;
  String? errorText;

  @override
  void initState() {
    super.initState();
    accountRefController = TextEditingController();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (accountRefController.text.isEmpty) {
      accountRefController.text = AppRuntimeScope.of(context).endUserRef;
    }
  }

  @override
  void dispose() {
    accountRefController.dispose();
    super.dispose();
  }

  Future<void> submit() async {
    final accountRef = accountRefController.text.trim();
    if (accountRef.isEmpty) {
      setState(() {
        errorText = 'Account reference is required.';
        resultText = null;
      });
      return;
    }

    setState(() {
      submitting = true;
      errorText = null;
      resultText = null;
    });

    try {
      final result = await AppRuntimeScope.of(
        context,
      ).client.submitAccountDelete(accountRef: accountRef);
      if (!mounted) {
        return;
      }
      setState(() {
        resultText =
            'Request ${result.deletionRequestId} accepted for ${result.accountRefMasked}.';
      });
    } on AppApiException catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        errorText = error.message;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        errorText = 'Deletion request failed. Please try again.';
      });
    } finally {
      if (mounted) {
        setState(() {
          submitting = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Delete Account')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Deletion request',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 12),
            const Text(
              'Submitting this request asks the tenant service team to remove account-linked data according to the tenant privacy policy.',
            ),
            const SizedBox(height: 16),
            TextField(
              controller: accountRefController,
              decoration: const InputDecoration(
                labelText: 'Account reference',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 20),
            if (resultText != null) ...[
              Text(
                resultText!,
                style: TextStyle(color: Theme.of(context).colorScheme.primary),
              ),
              const SizedBox(height: 12),
            ],
            if (errorText != null) ...[
              Text(
                errorText!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
              const SizedBox(height: 12),
            ],
            FilledButton(
              onPressed: submitting ? null : submit,
              child: Text(submitting ? 'Submitting...' : 'Submit request'),
            ),
          ],
        ),
      ),
    );
  }
}
